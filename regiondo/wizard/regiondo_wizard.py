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


    def _get_partner_id_from_regiondo_booking(self, booking, partner_id_by_regiondo_name):
        '''
        Find Odoo partner id from a reggiondo booking
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
                raise ValidationError(
                    _('Partner "%s" not found. Please check a customer is set with this "Regiondo name"')
                    % (partner_name,))

            key_partner = partner_id_by_regiondo_name[partner_name]
        return key_partner

    def _get_payment_mode_id_from_regiondo_booking(self, booking, payment_mode_id_by_regiondo_name):
        '''
        Find Odoo payment mode id from a regiondo booking
        '''
        # find payment_mode_key : booking['payment_status']['label']
        if booking['payment_status']['code'] == 'paid_offline':
            return None
        payment_mode_label = re.findall(r'\(([^]]*)\)', booking['payment_status']['label'])[0]
        if payment_mode_label not in payment_mode_id_by_regiondo_name:
            raise ValidationError(
                _('Payment mode "%s" not found. Please check a payment mode is set with this "Regiondo name"')
                % (payment_mode_label,))
        return payment_mode_id_by_regiondo_name[payment_mode_label]


    def _get_product_id_from_regiondo_booking(self, booking, product_id_by_regiondo_product_id):
        '''
        Find Odoo product id from a regiondo booking
        
        if several products in same booking : return None                
        '''
        regiondo_product_id = int(booking['product_id'])

        if regiondo_product_id not in product_id_by_regiondo_product_id:
            raise ValidationError(
                _('Product "%s" with id "%s" is not found. Please check "%s" product is created and '
                  '"regiondo product id" is set to "%s" for this product.')
                % (booking['product_name'], booking['product_id'], booking['product_name'], booking['product_id']))
        return product_id_by_regiondo_product_id[regiondo_product_id]

    def _get_invoice_line_value(self, booking, customer_id, product_id_by_regiondo_product_id):
        '''
        Build invoice line data from booking line
        '''

        # Build invoice line name
        invoice_line_name = ''
        # Booking number...
        invoice_line_name += booking['order_number'] + ' - '
        # Product name
        invoice_line_name += booking['ticket_name']
        if 'variation_name' in booking:
            invoice_line_name += ' ('+booking['variation_name']+')'
        invoice_line_name += ' - '
        # External booking number
        external_booking_number = booking['external_id']
        if external_booking_number:
            invoice_line_name += external_booking_number + ' - '
        # Event date
        invoice_line_name += booking['event_date_time'][:10] + ' - '
        # Name of final customer
        invoice_line_name += booking['first_name'] + ' ' + booking['last_name']

        # find external number if exists
        external_order_nomber_field_id = '21095'
        external_order_number = ''
        if 'buyer_data' in booking:
            for buyer_data in booking['buyer_data']:
                if buyer_data.get('field_id') == external_order_nomber_field_id:
                    external_order_number = buyer_data.get('value')
                    break
        
        if external_order_number:
            invoice_line_name += ' ['+external_order_number+']'


        # Find Prices and Quantity
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

        # Find product
        product_id = self._get_product_id_from_regiondo_booking(booking, product_id_by_regiondo_product_id)

        invoice_line_values = {
            'partner_id': customer_id,
            'product_id': product_id,
            'name': invoice_line_name,
            'quantity': qty,
            'price_unit': price_unit,
            'price_total': price_total,
            'tax_ids': [(6, 0, [self.env.company.account_sale_tax_id.id])],
        }

        return invoice_line_values

    def _get_invoices_data(self, regiondo_api_result, import_sequence):
        '''
        Build new invoices data from regiondo api result
        '''

        # Get all partner with regiondo_sales_channel_name
        partner_id_by_regiondo_name = {}
        partners = self.env['res.partner'].search([('regiondo_name', '!=', False)])
        for partner in partners:
            partner_id_by_regiondo_name[partner.regiondo_name] = partner.id


        # Get all payment mode with regiondo_name
        payment_mode_id_by_regiondo_name = {}
        payment_modes = self.env['account.payment.mode'].search([('regiondo_name', '!=', False)])
        for payment_mode in payment_modes:
            payment_mode_id_by_regiondo_name[payment_mode.regiondo_name] = payment_mode.id

        # Get all products with regiondo_product_id
        product_id_by_regiondo_product_id = {}
        products = self.env['product.product'].search([('product_tmpl_id.regiondo_product_id', '!=', False)])
        for product in products:
            product_id_by_regiondo_product_id[product.product_tmpl_id.regiondo_product_id] = product.id

        # Sort bookings_by_key[odoo_customer_id][odoo_payment_mode_id] = []
        '''        
        To find Partner key :
            if distribution partner (not POS), use it
            if distribution partner is POS : if reseller found use it, if reseller not found use "Web Customer"
        Partner Key is partner id associated with regiondo_name
        
        Payment mode key is Odoo Payment mode id with
        regiondo_name = data between brackets on booking['payment_status']['label']
        '''

        bookings_by_key = {}
        for booking in regiondo_api_result['data']:

            # find key partner from booking and partner_id indexed by regiondo_name
            key_partner = self._get_partner_id_from_regiondo_booking(booking, partner_id_by_regiondo_name)

            # initialise a new dict for this key partner
            if key_partner not in bookings_by_key:
                bookings_by_key[key_partner] = {}

            # find payment mode from booking and payment_mode_id indexed by regiondo_name
            key_payment_mode = self._get_payment_mode_id_from_regiondo_booking(booking,
                                                                               payment_mode_id_by_regiondo_name)

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
        invoices_data = []
        for customer_id, bookings_by_payment_mode in bookings_by_key.items():
            for payment_mode_id in bookings_by_payment_mode:
                invoice_lines_data = []

                for booking in bookings_by_key[customer_id][payment_mode_id]:
                    invoice_lines_data.append(self._get_invoice_line_value(booking, customer_id, product_id_by_regiondo_product_id))

                invoices_data.append({
                    'regiondo_import_code': import_sequence,
                    'move_type': 'out_invoice',
                    'payment_mode_id': payment_mode_id,
                    'partner_id': customer_id,
                    'invoice_line_ids': [(0, 0, d) for d in invoice_lines_data]
                })

        return invoices_data

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
        import_sequence = self.env['ir.sequence'].next_by_code('account.move.regiondo.import.code')

        # API connection parameters
        request_method = 'GET'
        public_key = self.env.company.regiondo_public_key
        private_key = self.env.company.regiondo_private_key
        accept_language = 'fr-FR'
        request_path = 'supplier/bookings'
        date_from = self.date_from
        date_to = self.date_to
        request_parameters = {
            'limit': 1000,
            'date_range_by': 'date_of_event',
            'date_range': '%s,%s' % (date_from, date_to),
        }

        # API call to get all bookings in selected period
        c = RegiondoConnector(public_key, private_key, accept_language)
        result = c.call(request_method, request_path, request_parameters)

        #check date
        if date_to < date_from:
            raise UserError(_('"date from" value is after "date to" value. '
                              'Please check dates.'))

        # check result limit
        if int(result['page']['total_items']) >= 250:
            raise UserError(_('Too many bookings for this date range. '
                              'Please change dates to reduce booking number.'
                              'Max bookings by query : 250'))
        
        # remove canceled bookings
        for idx, booking in enumerate(result['data']):
            if booking['status'] == 'canceled':
                result['data'].pop(idx)


        # get invoices data
        invoices_data = self._get_invoices_data(result, import_sequence)

        # create invoices
        for invoice in invoices_data:
            self.env['account.move'].create(invoice)

        # return to invoice tree view
        view_id = self.env.ref("account.view_out_invoice_tree").id
        return {
            "name": _("Import result"),
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            'view_id': view_id,
            'views': [(view_id, 'tree'), (False, 'form')],
            "domain": [["regiondo_import_code", "=", import_sequence]],
            'context': "{'default_move_type':'out_invoice'}",
        }
