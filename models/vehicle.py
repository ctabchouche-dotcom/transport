# -*- coding: utf-8 -*-
import secrets

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .crew import BUS_SIZES, LARGE_SEATS, SMALL_SEATS
from .seatmap import SEAT_LAYOUT_SELECTION


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    bus_size = fields.Selection(
        BUS_SIZES, string='Taille', compute='_compute_bus_size', store=True,
        help="Petit : 25 places ou moins. Moyen : jusqu'à 44. Grand : 45 et plus.",
    )
    seat_layout = fields.Selection(
        SEAT_LAYOUT_SELECTION,
        string='Alignement',
        help="Disposition réelle de ce bus : allée, porte, banquette ou coffre. "
             "Le plan public suit cet alignement quand le bus est affecté au départ.",
    )
    transport_device_token = fields.Char(
        string='Jeton du boîtier', copy=False, readonly=True, index=True,
        help="Secret du GPS et du lecteur QR fixés dans ce bus. "
             "Il est dans les deux adresses ci-dessous.",
    )
    device_position_url = fields.Char(
        string='Adresse GPS', compute='_compute_device_urls',
        help="Le boîtier GPS appelle cette adresse avec lat et lon. "
             "Exemple : l'adresse suivie de &lat=36.75&lon=3.04",
    )
    device_scan_url = fields.Char(
        string='Adresse du lecteur', compute='_compute_device_urls',
        help="Le lecteur fixe à la porte envoie le texte du QR (payload, code ou qr). "
             "Une réponse 200 accepte le passager. Toute autre réponse le refuse.",
    )
    last_latitude = fields.Float(string='Dernière latitude', digits=(9, 6), readonly=True)
    last_longitude = fields.Float(string='Dernière longitude', digits=(9, 6), readonly=True)
    last_tracked_at = fields.Datetime(string='Dernière position', readonly=True)

    _transport_device_token_unique = models.Constraint(
        'UNIQUE(transport_device_token)',
        'Ce jeton de boîtier est déjà utilisé.',
    )

    @api.depends('seats')
    def _compute_bus_size(self):
        for vehicle in self:
            seats = vehicle.seats or 0
            if seats <= 0:
                vehicle.bus_size = False
            elif seats <= SMALL_SEATS:
                vehicle.bus_size = 'small'
            elif seats < LARGE_SEATS:
                vehicle.bus_size = 'medium'
            else:
                vehicle.bus_size = 'large'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('transport_device_token'):
                vals['transport_device_token'] = secrets.token_hex(16)
        return super().create(vals_list)

    @api.model
    def _fill_device_tokens(self):
        missing = self.sudo().search([('transport_device_token', '=', False)])
        for vehicle in missing:
            vehicle.write({'transport_device_token': secrets.token_hex(16)})
        return True

    def _device_base_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        return base.rstrip('/')

    @api.depends('transport_device_token')
    def _compute_device_urls(self):
        base = self._device_base_url()
        dbname = self.env.cr.dbname
        for vehicle in self:
            token = vehicle.transport_device_token
            if not base or not token:
                vehicle.device_position_url = False
                vehicle.device_scan_url = False
                continue
            vehicle.device_position_url = '%s/bus/%s/position?db=%s' % (base, token, dbname)
            vehicle.device_scan_url = '%s/bus/%s/scan?db=%s' % (base, token, dbname)

    def device_departure(self):
        """The departure this bus is boarding or already running."""
        self.ensure_one()
        departure = self.env['transport.departure']
        running = departure.search([
            ('vehicle_id', '=', self.id),
            ('state', '=', 'in_progress'),
        ], order='departure_datetime, id', limit=1)
        if running:
            return running
        return departure.search([
            ('vehicle_id', '=', self.id),
            ('state', '=', 'boarding'),
        ], order='departure_datetime, id', limit=1)

    def device_record_position(self, latitude, longitude):
        """Store the tracker fix on the bus, and on the open departure when there is one."""
        self.ensure_one()
        latitude, longitude = self.env['transport.departure']._parse_coordinates(latitude, longitude)
        self.write({
            'last_latitude': latitude,
            'last_longitude': longitude,
            'last_tracked_at': fields.Datetime.now(),
        })
        departure = self.device_departure()
        if departure:
            departure.record_position(latitude, longitude)
        return departure

    def device_board(self, payload):
        self.ensure_one()
        departure = self.device_departure()
        if not departure:
            raise UserError(_("Ce bus n'a pas de départ en embarquement ou en course."))
        return self.env['transport.ticket'].board_payload(payload, departure)
