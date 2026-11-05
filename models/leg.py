# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class TransportLeg(models.Model):
    """One hop of a departure. Seat stock lives here, not on the vehicle."""

    _name = 'transport.leg'
    _description = 'Tronçon'
    _order = 'from_sequence, id'

    departure_id = fields.Many2one(
        'transport.departure', string='Départ', required=True, ondelete='cascade', index=True,
    )
    sequence = fields.Integer(required=True)
    from_sequence = fields.Integer(required=True, index=True)
    to_sequence = fields.Integer(required=True)
    origin_stop_id = fields.Many2one('transport.stop', string='De', required=True, ondelete='restrict')
    destination_stop_id = fields.Many2one('transport.stop', string='Vers', required=True, ondelete='restrict')
    seat_capacity = fields.Integer(string='Capacité', required=True)
    seats_taken = fields.Integer(string='Prises', compute='_compute_free')
    fill_percent = fields.Integer(string='Remplissage (%)', compute='_compute_free')
    seats_b2c_free = fields.Integer(string='Libres vente individuelle', compute='_compute_free')
    seats_b2b_free = fields.Integer(string='Libres entreprise', compute='_compute_free')

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('transport_build_legs'):
            raise UserError(_("Les tronçons sont créés avec le départ."))
        return super().create(vals_list)

    def write(self, vals):
        if set(vals) - {'seat_capacity'}:
            raise UserError(_("Les tronçons suivent les arrêts de la ligne."))
        return super().write(vals)

    def unlink(self):
        if not self.env.context.get('transport_build_legs'):
            raise UserError(_("Les tronçons suivent le départ."))
        return super().unlink()

    def _lock(self):
        """Block the hops so two sales cannot take the last seat together."""
        if not self:
            return
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT id FROM transport_leg WHERE id IN %s ORDER BY id FOR UPDATE",
            [tuple(sorted(self.ids))],
        )
        self.mapped('departure_id').invalidate_recordset(['booking_ids'])

    def booked_seats(self, channel=None, at=None, extra=0):
        self.ensure_one()
        at = at or fields.Datetime.now()
        total = extra
        bookings = self.departure_id.booking_ids
        if channel:
            bookings = bookings.filtered(lambda booking: booking.channel == channel)
        for booking in bookings:
            if booking._occupies_leg(self, at):
                total += booking.seat_count
        return total

    def free_seats(self, channel, at=None, extra_b2b=0, extra_b2c=0):
        """Seats still sellable on this hop for one channel.

        B2B can use the whole bus. B2C stays out of the company reserve
        until the departure's release time.
        """
        self.ensure_one()
        if channel not in ('b2c', 'b2b'):
            raise UserError(_("Canal de vente inconnu."))
        at = at or fields.Datetime.now()
        b2b = self.booked_seats('b2b', at, extra_b2b)
        b2c = self.booked_seats('b2c', at, extra_b2c)
        taken = b2b + b2c
        if channel == 'b2b':
            return self.seat_capacity - taken
        if self.departure_id.b2b_released(at):
            return self.seat_capacity - taken
        protected = max(0, self.departure_id.b2b_seat_reserve - b2b)
        return self.seat_capacity - taken - protected

    @api.depends(
        'seat_capacity',
        'departure_id.b2b_seat_reserve',
        'departure_id.release_datetime',
        'departure_id.booking_ids.state',
        'departure_id.booking_ids.seat_count',
        'departure_id.booking_ids.hold_until',
        'departure_id.booking_ids.channel',
        'departure_id.booking_ids.origin_sequence',
        'departure_id.booking_ids.destination_sequence',
    )
    def _compute_free(self):
        for leg in self:
            leg.seats_taken = leg.booked_seats()
            leg.fill_percent = round(leg.seats_taken * 100 / leg.seat_capacity) if leg.seat_capacity else 0
            leg.seats_b2c_free = max(leg.free_seats('b2c'), 0)
            leg.seats_b2b_free = max(leg.free_seats('b2b'), 0)
