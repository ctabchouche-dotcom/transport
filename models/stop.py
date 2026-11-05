# -*- coding: utf-8 -*-
from odoo import fields, models


class TransportStop(models.Model):
    _name = 'transport.stop'
    _description = 'Arrêt'
    _order = 'city, name, id'

    name = fields.Char(string='Nom', required=True)
    code = fields.Char(string='Code', required=True)
    city = fields.Char(string='Ville')
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint(
        'UNIQUE(code)',
        'Ce code d\'arrêt existe déjà.',
    )
