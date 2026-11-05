# -*- coding: utf-8 -*-
from odoo import fields, models

# Court : moins de 160 km. Moyen : jusqu'à 300 km. Long : au-delà.
SHORT_KM = 160
MEDIUM_KM = 300
# Petit : 25 places ou moins. Moyen : jusqu'à 44. Grand : 45 et plus.
SMALL_SEATS = 25
LARGE_SEATS = 45
MAX_DRIVE_HOURS = 8

ROUTE_LENGTHS = [
    ('short', 'Court'),
    ('medium', 'Moyen'),
    ('long', 'Long'),
]
BUS_SIZES = [
    ('small', 'Petit'),
    ('medium', 'Moyen'),
    ('large', 'Grand'),
]
LENGTH_TO_SIZE = {
    'short': 'small',
    'medium': 'medium',
    'long': 'large',
}


class TransportDriverRoute(models.Model):
    """One driver, one line. The same person does not own every departure of that line."""

    _name = 'transport.driver.route'
    _description = 'Itinéraire du chauffeur'
    _order = 'line_id, employee_id, id'

    employee_id = fields.Many2one(
        'hr.employee', string='Chauffeur', required=True, ondelete='cascade', index=True,
    )
    line_id = fields.Many2one(
        'transport.line', string='Itinéraire', required=True, ondelete='cascade', index=True,
    )
    company_id = fields.Many2one(related='employee_id.company_id', store=True)

    _employee_once = models.Constraint(
        'UNIQUE(employee_id)',
        'Ce chauffeur a déjà un itinéraire.',
    )
