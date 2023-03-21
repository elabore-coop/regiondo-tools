from odoo import models, fields, api, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    regiondo_name = fields.Char('Name in regiondo')

