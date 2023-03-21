from odoo import models, fields, api, _

class AccountMove(models.Model):
    _inherit = 'account.move'

    regiondo_import_code = fields.Char('Regiondo import code')
