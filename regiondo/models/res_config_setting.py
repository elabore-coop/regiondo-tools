from odoo import models, fields, api, _


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    regiondo_public_key = fields.Char(
        related="company_id.regiondo_public_key", string="Regiondo public key", readonly=False
    )
    regiondo_private_key = fields.Char(
        related="company_id.regiondo_private_key", string="Regiondo private key", readonly=False
    )
    regiondo_web_customer_id = fields.Many2one(
        related="company_id.regiondo_web_customer_id", string="Regiondo Web customer", readonly=False
    )


class Company(models.Model):
    _inherit = "res.company"

    regiondo_public_key = fields.Char(string="Regiondo public key")
    regiondo_private_key = fields.Char(string="Regiondo private key")
    regiondo_web_customer_id = fields.Many2one('res.partner', string="Regiondo web customer", help="When import invoices from Regiondo, if no resseler and POS sale channel, select this customer")


    @api.model
    def setting_init_regiondo_import_wizard_action(self):
        """ Called by the 'Import' button in Invoice/Actions"""
        view_id = self.env.ref('regiondo.regiondo_import_wizard_view').id
        return {'type': 'ir.actions.act_window',
                'name': _('Import invoices from Regiondo'),
                'res_model': 'regiondo.import.wizard',
                'target': 'new',
                'view_mode': 'form',
                'views': [[view_id, 'form']],
                }
