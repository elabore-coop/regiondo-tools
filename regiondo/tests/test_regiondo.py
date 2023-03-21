import logging
import unittest
import json


from odoo.tests.common import SavepointCase, HttpSavepointCase, tagged, Form, TransactionCase, SavepointCase
from odoo.modules.module import get_module_resource


@tagged('-standard', 'regiondo')
class TestRegiondo(SavepointCase):

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super(TestRegiondo, cls).setUpClass()
        cls.wizard = cls.env['regiondo.import.wizard']
        cls.import_sequence = cls.env['ir.sequence'].next_by_code('account.move.regiondo.import.code')


    def test_import(self):

        # load sample files
        api_response_file_path = get_module_resource('regiondo', 'static/tests', 'regiondo_api_response_sample.json')
        with open(api_response_file_path) as api_response_file:
            fake_api_response = json.load(api_response_file)

        # set import sequence
        self.import_sequence = '0000076'

        # test _get_invoices_data
        invoices_data = self.wizard._get_invoices_data(fake_api_response, self.import_sequence)

        # test number of bookings = number of invoice lines
        number_of_bookings = len(fake_api_response['data'])
        number_of_invoice_line = 0
        for invoice_data in invoices_data:
            number_of_invoice_line += len(invoice_data['invoice_line_ids'])
        self.assertEqual(number_of_bookings, number_of_invoice_line)


        # test total amount, price_unit, quantity
        total_amount_regiondo = 0
        for booking in fake_api_response['data']:
            total_amount_regiondo += float(booking['total_amount'])

        total_amount_invoices = 0
        for invoice_data in invoices_data:
            for invoice_line_data in invoice_data['invoice_line_ids']:
                total_amount_invoices += invoice_line_data[2]['price_unit']*invoice_line_data[2]['quantity']
        self.assertEqual(total_amount_regiondo, total_amount_invoices)



