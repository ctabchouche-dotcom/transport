# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .crew import MEDIUM_KM, ROUTE_LENGTHS, SHORT_KM
from .seatmap import SEAT_LAYOUT_SELECTION, build_seat_plan, layout_fits


class TransportLine(models.Model):
    _name = 'transport.line'
    _description = 'Ligne'
    _inherit = ['mail.thread']
    _order = 'code, id'

    name = fields.Char(string='Nom', required=True, tracking=True)
    code = fields.Char(string='Code', required=True, tracking=True)
    line_type = fields.Selection(
        [
            ('b2c', 'Interurbain'),
            ('b2b', 'Navette entreprise'),
            ('hybrid', 'Hybride'),
        ],
        string='Type',
        required=True,
        default='hybrid',
        tracking=True,
    )
    seat_capacity = fields.Integer(
        string='Capacité type', required=True, default=49, tracking=True,
        help="Nombre de places copié sur chaque nouveau départ, avant affectation du bus.",
    )
    seat_layout = fields.Selection(
        SEAT_LAYOUT_SELECTION,
        string='Alignement',
        tracking=True,
        help="Plan du car tant qu'aucun bus n'est affecté au départ. "
             "Le bus affecté impose son propre alignement.",
    )
    b2b_seat_reserve = fields.Integer(
        string='Réserve entreprise', default=0, tracking=True,
        help="Places tenues pour les abonnés jusqu'à l'heure de libération. "
             "Passé ce délai, l'invendu repasse à la vente individuelle.",
    )
    release_hours = fields.Integer(
        string='Libération (heures avant le départ)', default=2, tracking=True,
    )
    average_speed = fields.Integer(
        string='Vitesse moyenne (km/h)', default=70, tracking=True,
        help="Sert à calculer l'heure de passage à chaque arrêt à partir des distances.",
    )
    distance_km = fields.Float(
        string='Distance (km)', compute='_compute_distance_km', store=True,
        help="Somme des kilomètres depuis l'arrêt précédent.",
    )
    route_length_force = fields.Selection(
        ROUTE_LENGTHS, string='Longueur imposée', tracking=True,
        help="Vide : la longueur suit la distance. Court en dessous de 160 km, "
             "moyen en dessous de 300 km, long au-delà.",
    )
    route_length = fields.Selection(
        ROUTE_LENGTHS, string='Longueur', compute='_compute_route_length', store=True,
    )
    drive_hours = fields.Float(
        string='Conduite (h)', compute='_compute_drive_hours', store=True, digits=(16, 2),
        help="Distance divisée par la vitesse moyenne. Un chauffeur ne dépasse pas 8 h par jour.",
    )
    driver_route_ids = fields.One2many(
        'transport.driver.route', 'line_id', string='Chauffeurs de l\'itinéraire',
    )
    fare = fields.Float(
        string='Prix bout en bout', default=0, tracking=True,
        help="Prix indicatif du trajet complet. La vente en ligne utilise les tarifs par montée et descente.",
    )
    cancel_hours = fields.Integer(
        string='Annulation (heures avant le départ)', default=24, tracking=True,
    )
    refund_percent = fields.Integer(
        string='Remboursement (%)', default=100, tracking=True,
    )
    fare_ids = fields.One2many('transport.fare', 'line_id', string='Tarifs')
    company_id = fields.Many2one(
        'res.company', string='Société', required=True, default=lambda self: self.env.company,
    )
    stop_ids = fields.One2many('transport.line.stop', 'line_id', string='Arrêts', copy=True)
    schedule_ids = fields.One2many('transport.schedule', 'line_id', string='Horaires', copy=True)
    active = fields.Boolean(default=True)
    departure_count = fields.Integer(compute='_compute_departure_count')

    _code_unique = models.Constraint(
        'UNIQUE(code)',
        'Ce code de ligne existe déjà.',
    )
    _capacity_positive = models.Constraint(
        'CHECK(seat_capacity > 0)',
        'La capacité doit être positive.',
    )
    _reserve_within_capacity = models.Constraint(
        'CHECK(b2b_seat_reserve >= 0 AND b2b_seat_reserve <= seat_capacity)',
        'La réserve entreprise doit tenir dans la capacité.',
    )
    _release_positive = models.Constraint(
        'CHECK(release_hours >= 0)',
        "Le délai de libération ne peut pas être négatif.",
    )
    _speed_positive = models.Constraint(
        'CHECK(average_speed > 0)',
        'La vitesse moyenne doit être positive.',
    )
    _fare_positive = models.Constraint(
        'CHECK(fare >= 0)',
        'Le prix d\'une place ne peut pas être négatif.',
    )
    _cancel_positive = models.Constraint(
        'CHECK(cancel_hours >= 0)',
        "Le délai d'annulation ne peut pas être négatif.",
    )
    _refund_percent_range = models.Constraint(
        'CHECK(refund_percent >= 0 AND refund_percent <= 100)',
        'Le remboursement est un pourcentage entre 0 et 100.',
    )

    @api.depends('stop_ids.distance_km')
    def _compute_distance_km(self):
        for line in self:
            line.distance_km = sum(line.stop_ids.mapped('distance_km'))

    @api.depends('distance_km', 'route_length_force')
    def _compute_route_length(self):
        for line in self:
            if line.route_length_force:
                line.route_length = line.route_length_force
                continue
            km = line.distance_km or 0.0
            if km < SHORT_KM:
                line.route_length = 'short'
            elif km < MEDIUM_KM:
                line.route_length = 'medium'
            else:
                line.route_length = 'long'

    @api.depends('distance_km', 'average_speed')
    def _compute_drive_hours(self):
        for line in self:
            speed = line.average_speed or 70
            line.drive_hours = (line.distance_km or 0.0) / speed

    def _compute_departure_count(self):
        grouped = self.env['transport.departure']._read_group(
            [('line_id', 'in', self.ids)],
            ['line_id'],
            ['__count'],
        )
        counts = {line.id: count for line, count in grouped}
        for line in self:
            line.departure_count = counts.get(line.id, 0)

    @api.model
    def build_seat_plan(self, layout, capacity, taken=None):
        return build_seat_plan(layout, capacity, taken)

    @api.model
    def layout_fits(self, layout, capacity):
        return layout_fits(layout, capacity)

    def price_between(self, origin, destination):
        """Price of one seat from origin to destination, in dinars."""
        self.ensure_one()
        fare = self.env['transport.fare'].search([
            ('line_id', '=', self.id),
            ('origin_stop_id', '=', origin.id),
            ('destination_stop_id', '=', destination.id),
        ], limit=1)
        if not fare or fare.price <= 0:
            raise UserError(_("Ce trajet n'a pas de prix."))
        return fare.price

    def action_view_departures(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Départs'),
            'res_model': 'transport.departure',
            'view_mode': 'list,form',
            'domain': [('line_id', '=', self.id)],
            'context': {'default_line_id': self.id},
        }

    def action_auto_assign_open(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        departures = self.env['transport.departure'].search([
            ('line_id', '=', self.id),
            ('state', '=', 'planned'),
            ('service_date', '>=', today),
        ])
        if not departures:
            raise UserError(_("Aucun départ planifié à venir."))
        return departures.action_auto_assign()

    def action_open_generate(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Générer les départs'),
            'res_model': 'transport.departure.generate',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_line_id': self.id},
        }

    def action_open_close_day(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fermer une journée'),
            'res_model': 'transport.departure.close',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_line_id': self.id},
        }

    def _leg_commands(self, seat_capacity):
        self.ensure_one()
        stops = self.stop_ids.sorted('sequence')
        if len(stops) < 2:
            raise UserError(_("La ligne %s doit avoir au moins deux arrêts.", self.display_name))
        commands = []
        for left, right in zip(stops, stops[1:]):
            commands.append((0, 0, {
                'sequence': left.sequence,
                'from_sequence': left.sequence,
                'to_sequence': right.sequence,
                'origin_stop_id': left.stop_id.id,
                'destination_stop_id': right.stop_id.id,
                'seat_capacity': seat_capacity,
            }))
        return commands

    def generate_departures(self, date_from, date_to):
        """Create the missing departures of this line between two dates."""
        self.ensure_one()
        if not self.active:
            raise UserError(_("Cette ligne est archivée."))
        if not date_from or not date_to or date_to < date_from:
            raise UserError(_("La période de génération est invalide."))
        if (date_to - date_from).days > 366:
            raise UserError(_("Générez au plus 366 jours à la fois."))
        if len(self.stop_ids) < 2:
            raise UserError(_("Ajoutez au moins deux arrêts avant de générer des départs."))
        schedules = self.schedule_ids.filtered('active')
        if not schedules:
            raise UserError(_("Ajoutez un horaire actif."))
        created = self.env['transport.departure']
        day = date_from
        while day <= date_to:
            for schedule in schedules:
                if not schedule.matches(day):
                    continue
                departure_datetime = schedule.as_datetime(day)
                already = self.env['transport.departure'].search_count([
                    ('line_id', '=', self.id),
                    ('departure_datetime', '=', departure_datetime),
                    ('state', '!=', 'cancelled'),
                ])
                if already:
                    continue
                created |= self.env['transport.departure'].create({
                    'line_id': self.id,
                    'schedule_id': schedule.id,
                    'departure_datetime': departure_datetime,
                })
            day += timedelta(days=1)
        return created

    def unlink(self):
        busy = self.env['transport.departure'].search_count([('line_id', 'in', self.ids)])
        if busy:
            raise UserError(_("Archivez la ligne : des départs y sont rattachés."))
        return super().unlink()


class TransportLineStop(models.Model):
    _name = 'transport.line.stop'
    _description = 'Arrêt de ligne'
    _order = 'sequence, id'

    line_id = fields.Many2one(
        'transport.line', string='Ligne', required=True, ondelete='cascade', index=True,
    )
    stop_id = fields.Many2one('transport.stop', string='Arrêt', required=True, ondelete='restrict')
    sequence = fields.Integer(string='Ordre', default=10)
    distance_km = fields.Float(string='Km depuis l\'arrêt précédent')
    boarding = fields.Boolean(string='Montée', default=True)
    alighting = fields.Boolean(string='Descente', default=True)

    _stop_once = models.Constraint(
        'UNIQUE(line_id, stop_id)',
        'Cet arrêt est déjà sur la ligne.',
    )
    _sequence_once = models.Constraint(
        'UNIQUE(line_id, sequence)',
        'Deux arrêts ne peuvent pas avoir la même position.',
    )
    _distance_positive = models.Constraint(
        'CHECK(distance_km >= 0)',
        'La distance depuis l\'arrêt précédent ne peut pas être négative.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        lines = self.env['transport.line'].browse([
            vals['line_id'] for vals in vals_list if vals.get('line_id')
        ])
        self._check_lines(lines)
        next_sequence = {}
        for vals in vals_list:
            if vals.get('sequence'):
                continue
            line_id = vals.get('line_id')
            if line_id not in next_sequence:
                last = self.search([('line_id', '=', line_id)], order='sequence desc', limit=1)
                next_sequence[line_id] = (last.sequence or 0) + 10
            vals['sequence'] = next_sequence[line_id]
            next_sequence[line_id] += 10
        return super().create(vals_list)

    def write(self, vals):
        locked = {'line_id', 'stop_id', 'sequence', 'boarding', 'alighting'}
        if locked & set(vals):
            self._check_lines(self.mapped('line_id'))
        return super().write(vals)

    def unlink(self):
        self._check_lines(self.mapped('line_id'))
        return super().unlink()

    def _check_lines(self, lines):
        if not lines:
            return
        busy = self.env['transport.departure'].search_count([
            ('line_id', 'in', lines.ids),
            ('state', '!=', 'cancelled'),
        ])
        if busy:
            raise UserError(_(
                "Cette ligne a des départs non annulés. Annulez-les avant de modifier les arrêts.",
            ))


class TransportFare(models.Model):
    _name = 'transport.fare'
    _description = 'Tarif'
    _order = 'line_id, origin_stop_id, destination_stop_id, id'

    line_id = fields.Many2one(
        'transport.line', string='Ligne', required=True, ondelete='cascade', index=True,
    )
    origin_stop_id = fields.Many2one('transport.stop', string='Montée', required=True, ondelete='restrict')
    destination_stop_id = fields.Many2one('transport.stop', string='Descente', required=True, ondelete='restrict')
    price = fields.Float(string='Prix d\'une place', required=True)

    _pair_once = models.Constraint(
        'UNIQUE(line_id, origin_stop_id, destination_stop_id)',
        'Ce trajet a déjà un tarif.',
    )
    _price_positive = models.Constraint(
        'CHECK(price >= 0)',
        'Le prix d\'une place ne peut pas être négatif.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_pair()
        return records

    def write(self, vals):
        result = super().write(vals)
        if {'line_id', 'origin_stop_id', 'destination_stop_id'} & set(vals):
            self._check_pair()
        return result

    def _check_pair(self):
        for fare in self:
            sequences = {
                stop.stop_id.id: stop.sequence for stop in fare.line_id.stop_ids
            }
            origin = sequences.get(fare.origin_stop_id.id)
            destination = sequences.get(fare.destination_stop_id.id)
            if origin is None or destination is None or origin >= destination:
                raise UserError(_(
                    "Le tarif va d'un arrêt amont vers un arrêt aval de la ligne.",
                ))
