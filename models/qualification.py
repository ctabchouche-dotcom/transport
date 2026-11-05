# -*- coding: utf-8 -*-
from odoo import fields, models

DOCUMENT_TYPES = [
    ('license', 'Permis'),
    ('medical', 'Visite médicale'),
    ('training', 'Formation'),
]


class TransportDriverDocument(models.Model):
    _name = 'transport.driver.document'
    _description = 'Habilitation chauffeur'
    _order = 'expires_on, id'

    employee_id = fields.Many2one(
        'hr.employee', string='Chauffeur', required=True, ondelete='cascade', index=True,
    )
    doc_type = fields.Selection(DOCUMENT_TYPES, string='Type', required=True)
    reference = fields.Char(string='Référence')
    expires_on = fields.Date(string='Expire le', required=True, index=True)

    _type_once = models.Constraint(
        'UNIQUE(employee_id, doc_type)',
        'Ce chauffeur a déjà ce type d\'habilitation. Mettez la date à jour.',
    )
