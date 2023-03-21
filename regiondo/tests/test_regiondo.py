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

        #load sample files
        api_response_file_path = get_module_resource('regiondo', 'static/tests', 'regiondo_api_response_sample.json')
        expected_invoices_data_file_path = get_module_resource('regiondo', 'static/tests', 'regiondo_api_response_sample.json')
        with open(api_response_file_path) as api_response_file:
            fake_api_response = json.load(api_response_file)
            with open(expected_invoices_data_file_path) as expected_invoices_data_file:
                expected_invoices_data = json.load(expected_invoices_data_file)

        # test _get_invoices_data
        invoices_data = self.wizard._get_invoices_data(fake_api_response, self.import_sequence)
        self.assertEqual(
            invoices_data,
            expected_invoices_data)

        self.assertEqual(1, 2)







