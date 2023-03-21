from odoo import models, fields, api, _



class ProductTemplate(models.Model):
    _inherit = 'product.template'

    regiondo_product_id = fields.Integer('Regiondo product id')
