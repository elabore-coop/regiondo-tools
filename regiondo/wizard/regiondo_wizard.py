from datetime import date, timedelta
from odoo import models, fields, _
from ..tools.regiondoconnector import RegiondoConnector
import pprint
import logging
import json
from odoo.exceptions import AccessError, MissingError, ValidationError, UserError
import re

class RegiondoImportWizard(models.TransientModel):
    _name = 'regiondo.import.wizard'

    '''
        Default dates are set to import all bookings of last month
    '''
    def _default_date_from(self):
        today = date.today()
        first_of_month = today.replace(day=1)
        previous_month = first_of_month - timedelta(days=1)
        return previous_month.replace(day=1)

    def _default_date_to(self):
        today = date.today()
        first_of_month = today.replace(day=1)
        return first_of_month - timedelta(days=1)

    date_from = fields.Date('From', default=lambda self: self._default_date_from())
    date_to = fields.Date('To', default=lambda self: self._default_date_to())



    def import_invoices(self):
        """
        Import all bookings from Regiondo API in selected period.

        Function does :
            1- Build a Dict bookings_by_key[key_partner][key_payment_mode] = [bookings] from API result
            2- Create an invoice by partner and by payment mode with lines corresponding to all bookings

        Import specifications :
            Invoice line name = order number + product label + external comment + event date + end user name
            Mapping products, partners, payment mode with regiondo fields in Odoo
            Customer mapping with :
                if Sale Channel is POS
                    if label in ['payment_status']['offline_amounts'][0]['label'] : use it
                    else use "Web Customer"
                else use Sale Channel Name

        :return: tree view of created invoices
        """
        _logger = logging.getLogger(__name__)

        # a sequence for each import, used to filter invoices at the end
        import_code = self.env['ir.sequence'].next_by_code('account.move.regiondo.import.code')

        # API connection parameters
        request_method = 'GET'
        public_key = self.env.company.regiondo_public_key
        private_key = self.env.company.regiondo_private_key
        accept_language = 'fr-FR'
        request_path = 'supplier/bookings'
        date_from = self.date_from
        date_to = self.date_to
        request_parameters = {
            'limit': 50,
            'date_range_by': 'date_bought',
            'date_range': '%s,%s' % (date_from, date_to),
        }

        # Get all partner with regiondo_sales_channel_name
        partner_id_by_regiondo_name = {}
        partners = self.env['res.partner'].search([('regiondo_name','!=',False)])
        for partner in partners:
            partner_id_by_regiondo_name[partner.regiondo_name] = partner.id

        # Get all payment mode with regiondo_name
        payment_mode_id_by_regiondo_name = {}
        payment_modes = self.env['account.payment.mode'].search([('regiondo_name', '!=', False)])
        for payment_mode in payment_modes:
            payment_mode_id_by_regiondo_name[payment_mode.regiondo_name] = payment_mode.id

        # API call to get all bookings in selected period
        c = RegiondoConnector(public_key, private_key, accept_language)
        result = c.call(request_method, request_path, request_parameters)

        # build bookings_by_key
        bookings_by_key = {}
        for booking in result['data']:

            ''' 
            How to find Partner key :
                    if distribution partner (not POS), use it
                    if distribution partner is POS : if reseller found use it, if reseller not found use "Web Customer"
            Partner Key is associated partner id
            '''
            key_partner = None
            if booking['distribution_channel_partner'] == 'POS':
                # _logger.debug('Booking = %s',booking)

                if 'payment_status' in booking and 'offline_amounts' in booking['payment_status']:
                    partner_name = booking['payment_status']['offline_amounts'][0]['label']
                else:
                    key_partner = self.env.company.regiondo_web_customer_id.id
            else:
                partner_name = booking['distribution_channel_partner']

            if not key_partner:
                if partner_name not in partner_id_by_regiondo_name:
                    raise ValidationError('Partner %s not found. Please check a customer is set with this "Regiondo name"'
                                          % (partner_name, ))

                key_partner = partner_id_by_regiondo_name[partner_name]

            # initialise a new dict for this key partner
            if key_partner not in bookings_by_key:
                bookings_by_key[key_partner] = {}

            # find payment_mode_key : booking['payment_status']['label']
            payment_mode_label = re.findall(r'\(([^]]*)\)', booking['payment_status']['label'])[0]
            if payment_mode_label not in payment_mode_id_by_regiondo_name:
                _logger.debug('Payment mode "%s" not in "%s"', payment_mode_label, payment_mode_id_by_regiondo_name)
                raise ValidationError('Payment mode %s is not found. Please check a payment mode is set with this "Regiondo name"'
                                      % (payment_mode_label,))
            key_payment_mode = payment_mode_id_by_regiondo_name[payment_mode_label]

            # initialise a new array for this payment mode
            if key_payment_mode not in bookings_by_key[key_partner]:
                bookings_by_key[key_partner][key_payment_mode] = []

            bookings_by_key[key_partner][key_payment_mode].append(booking)

        # find details for each booking
        '''
        In the future if we want more details for a booking, uncomment this
        
        
        for key_partner in bookings_by_key:
            for key_payment_mode in bookings_by_key[key_partner]:
                # Call checkout/booking to get details of booking (unit price, discount...)
                for booking in bookings_by_key[key_partner][key_payment_mode]:
                    result_detail = c.call(request_method, request_path_details, {'booking_key': booking['booking_key']})
                    booking['details'] = result_detail
        '''

        # Create invoices with an invoice line by booking
        for customer_id in bookings_by_key:
            for payment_mode_id in bookings_by_key[customer_id]:

                invoice_line_data = []

                for booking in bookings_by_key[customer_id][payment_mode_id]:

                    # Build invoice line name
                    invoice_line_name = ''
                    # Booking number...
                    invoice_line_name += booking['order_number'] + ' - '
                    # Product name
                    invoice_line_name += booking['ticket_name'] + ' - '
                    # External booking number
                    external_booking_number = booking['external_id']
                    if external_booking_number:
                        invoice_line_name += external_booking_number + ' - '
                    # Event date
                    invoice_line_name += booking['event_date_time'][:10] + ' - '
                    # Name of final customer
                    invoice_line_name += booking['first_name']+' '+booking['last_name']

                    price_unit = 0
                    qty = 0
                    price_total = 0
                    discount_amount = 0

                    if len(booking['options']) > 1:
                        # case of several products : qté = 1 ; price unit = price total
                        price_unit = price_total = float(booking['total_amount'])
                        qty = 1
                    else:
                        # case one product
                        qty = float(booking['qty'])
                        price_total = float(booking['total_amount'])
                        price_unit = price_total / qty

                    invoice_line_values = {
                        'partner_id': customer_id,
                        'name': invoice_line_name,
                        'quantity': qty,
                        'price_unit': price_unit,
                        'price_total': price_total,
                        'tax_ids': self.env.company.account_sale_tax_id,
                    }

                    invoice_line_data.append(invoice_line_values)


                #create invoice
                self.env['account.move'].create({
                    'regiondo_import_code': import_code,
                    'move_type': 'out_invoice',
                    'payment_mode_id': payment_mode_id,
                    'partner_id': customer_id,
                    'invoice_line_ids': [(0, 0, d) for d in invoice_line_data]
                })

        return {
            "name": _("Import result"),
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "views": [[False, "tree"], [False, "form"]],
            "domain": [["regiondo_import_code", "=", import_code]],
        }
