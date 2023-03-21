from odoo import models, fields, api, _


class AccountPaymentMode(models.Model):
    _inherit = 'account.payment.mode'

    regiondo_name = fields.Char('Name in regiondo')

