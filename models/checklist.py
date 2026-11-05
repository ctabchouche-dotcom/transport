# -*- coding: utf-8 -*-
from odoo import fields, models


class TransportCheckTemplate(models.Model):
    _name = 'transport.check.template'
    _description = 'Point de contrôle'
    _order = 'sequence, id'

    name = fields.Char(string='Contrôle', required=True)
    sequence = fields.Integer(default=10)
    critical = fields.Boolean(
        string='Critique',
        default=True,
        help="Un contrôle critique non conforme empêche le passage en course.",
    )
    active = fields.Boolean(default=True)


class TransportDepartureCheck(models.Model):
    _name = 'transport.departure.check'
    _description = 'Contrôle de pré-départ'
    _order = 'sequence, id'

    departure_id = fields.Many2one(
        'transport.departure', string='Départ', required=True, ondelete='cascade', index=True,
    )
    template_id = fields.Many2one(
        'transport.check.template', string='Point de contrôle', required=True, ondelete='restrict',
    )
    name = fields.Char(related='template_id.name', store=True)
    sequence = fields.Integer(related='template_id.sequence', store=True)
    critical = fields.Boolean(related='template_id.critical', store=True)
    result = fields.Selection(
        [
            ('pending', 'À faire'),
            ('ok', 'Conforme'),
            ('ko', 'Défectueux'),
        ],
        string='Résultat',
        default='pending',
        required=True,
    )
