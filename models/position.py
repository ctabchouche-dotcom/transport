# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class TransportPosition(models.Model):
    _name = 'transport.position'
    _description = 'Position GPS'
    _order = 'recorded_at desc, id desc'

    departure_id = fields.Many2one(
        'transport.departure', string='Départ', required=True, ondelete='cascade', index=True,
    )
    vehicle_id = fields.Many2one('fleet.vehicle', string='Bus')
    latitude = fields.Float(string='Latitude', digits=(9, 6), required=True)
    longitude = fields.Float(string='Longitude', digits=(9, 6), required=True)
    recorded_at = fields.Datetime(string='Reçue le', required=True, default=fields.Datetime.now)

    _latitude_range = models.Constraint(
        'CHECK(latitude >= -90 AND latitude <= 90)',
        'La latitude est entre -90 et 90.',
    )
    _longitude_range = models.Constraint(
        'CHECK(longitude >= -180 AND longitude <= 180)',
        'La longitude est entre -180 et 180.',
    )
