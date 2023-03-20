import logging
import unittest
import json


from odoo.tests.common import SavepointCase, HttpSavepointCase, tagged, Form, SingleTransactionCase
from odoo.modules.module import get_module_resource

@tagged('-standard', 'regiondo')
class TestRegiondo(SingleTransactionCase):

    def test_import(self):
        json_file_path = get_module_resource('regiondo', 'static/tests', 'regiondo_response_example.json')
        with open(json_file_path) as f:
            data = json.load(f)



