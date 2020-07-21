# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.addons import decimal_precision as dp
from datetime import datetime, date


class StockInventoryEvaluation(models.Model):
    _name = 'stock.inventory.evaluation'

    def action_cancel_draft(self):
        self.write({
            'line_ids': [(5,)],
            'state': 'draft'
        })

    @api.model
    def _default_location_id(self):
        company_user = self.env.user.company_id
        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', company_user.id)], limit=1)
        if warehouse:
            return warehouse.lot_stock_id.id
        else:
            raise UserError(
                _('You must define a warehouse for the company: %s.') % (
                    company_user.name,))

    name = fields.Char()
    date = fields.Datetime(string='Date', required=True)
    line_history_ids = fields.One2many(
        'product.cost.evaluation.history', 'inventory_evaluation_id',
        string='Inventories',
        copy=True, readonly=False,
        states={'done': [('readonly', True)]})
    line_ids = fields.One2many(
        'stock.inventory.evaluation.line', 'inventory_id', string='Inventories',
        copy=True, readonly=False,
        states={'done': [('readonly', True)]})
    company_id = fields.Many2one(
        'res.company', 'Company',
        readonly=True, index=True, required=True,
        states={'draft': [('readonly', False)]},
        default=lambda self: self.env['res.company']._company_default_get(
            'stock.inventory'))
    state = fields.Selection(string='Status', selection=[
        ('draft', 'Draft'),
        ('cancel', 'Cancelled'),
        ('done', 'Done')],
                             copy=False, index=True, readonly=True,
                             default='draft')
    location_id = fields.Many2one(
        'stock.location', 'Inventoried Location',
        readonly=True, required=True,
        states={'draft': [('readonly', False)]},
        default=_default_location_id)

    def action_start(self):
        for inventory in self.filtered(lambda x: x.state not in ('done', 'cancel')):
            if not inventory.line_ids:
                inventory._get_inventory_lines_values_new()
        return True

    def _get_inventory_lines_values_new(self):
        product_model = self.env['product.product']
        product_ids = product_model.search([('type', '=', 'product')])
        res = product_ids._compute_quantities_at_date(self.location_id, self.date)
        self.create_inventory_line(res)
        self.get_last_purchase_cost()
        self.get_totals_from_line()
        self.get_average_purchase_cost()

    def create_inventory_line(self, res):
        product_model = self.env['product.product']
        product_cost_eval_history_model = self.env[
            'product.cost.evaluation.history']
        for element in res:
            product = product_model.browse(element)
            vals = {'name': self.name,
                    'product_id': element,
                    'product_qty': res[element]['qty_available'],
                    'location_id': self.location_id.id,
                    'date_evaluation': self.date,
                    'standard_cost': product.standard_price,
                    'list_price': product.list_price,
                    'inventory_evaluation_id': self.id}
            product_cost_eval_history_model.create(vals)

    def get_last_purchase_cost(self):
        inventoried_location = self.location_id.id
        for line in self.line_history_ids:
            domain = [
                ('company_id', '=', self.env.user.company_id.id),
                ('date', '<=', self.date),
                ('state', '=', 'done'),
                ('purchase_line_id', '!=', False),
                ('product_id', '=', line.product_id.id),
                '|',
                ('location_id.usage', '=', 'internal'),
                ('location_dest_id.usage', '=', 'internal'),
                '|',
                ('location_id', '=', inventoried_location),
                ('location_dest_id', '=', inventoried_location),
            ]
            move_obj = self.env['stock.move']
            move_ids = move_obj.search(domain)
            index = 0
            purchase_info = {'last_date': '', 'purchase_cost': 0}
            for move in move_ids:
                index += 1
                if move.purchase_line_id.invoice_lines:
                    inv_lines = move.purchase_line_id.invoice_lines.filtered(lambda x: x.invoice_id.state in ['open', 'paid'])
                    if inv_lines:
                        if move.purchase_line_id.qty_invoiced > 0:
                            line_sorted = inv_lines.sorted(key=lambda l: l.invoice_id.date_invoice, reverse=True)
                            if index == 1:
                                purchase_info['last_date'] = line_sorted[0].invoice_id.date_invoice
                                purchase_info['purchase_cost'] = line_sorted[0].price_unit
                            else:
                                if type(purchase_info['last_date']) == date:
                                    if line_sorted[0].invoice_id.date_invoice > purchase_info['last_date']:
                                        purchase_info['last_date'] = line_sorted[0].invoice_id.date_invoice
                                        purchase_info['purchase_cost'] = line_sorted[0].price_unit
            line.last_purchase_cost = purchase_info['purchase_cost']

    def get_totals_from_line(self):
        for line in self.line_history_ids:
            total_qty, total_value = self.compute_totals(line.product_id)
            line.purchase_qty = total_qty
            line.purchase_value = total_value

    def compute_totals(self, product):
        inventoried_location = self.location_id.id
        total_qty = 0
        total_cost = 0
        domain = [
            ('company_id', '=', self.env.user.company_id.id),
            ('date', '<=', self.date),
            ('state', '=', 'done'),
            ('purchase_line_id', '!=', False),
            ('product_id', '=', product.id),
            '|',
            ('location_id.usage', '=', 'internal'),
            ('location_dest_id.usage', '=', 'internal'),
            '|',
            ('location_id', '=', inventoried_location),
            ('location_dest_id', '=', inventoried_location),
        ]
        move_obj = self.env['stock.move']
        move_ids = move_obj.search(domain)
        for move in move_ids:
            if move.purchase_line_id.invoice_lines:
                inv_lines = move.purchase_line_id.invoice_lines.filtered(
                    lambda x: x.invoice_id.state in ['open', 'paid'])
                if inv_lines:
                    for line in inv_lines:
                        if move.location_id.usage == 'internal' and move.location_dest_id.usage != 'internal':
                            total_cost -= line.price_subtotal
                            total_qty -= line.quantity
                        elif move.location_dest_id.usage == 'internal' and move.location_id.usage != 'internal':
                            total_cost += line.price_subtotal
                            total_qty += line.quantity
        return total_qty, total_cost

    def get_average_purchase_cost(self):
        count_product = {}
        for line in self.line_history_ids:
            if line.product_id.id not in count_product.keys():
                if line.purchase_qty > 0:
                    average_purchase_cost = line.purchase_value / line.purchase_qty
                    count_product[line.product_id.id] = average_purchase_cost
                else:
                    count_product[line.product_id.id] = 0
            line.average_purchase_cost = count_product[line.product_id.id]

    @api.multi
    def action_cancel(self):
        for stock in self:
            stock.state = 'cancel'

    @api.multi
    def action_done(self):
        for stock in self:
            stock.state = 'done'


class InventoryLine(models.TransientModel):
    _name = "stock.inventory.evaluation.line"
    _description = "Inventory Evaluation Line"
    _order = "product_id, inventory_id, location_id, prod_lot_id"

    inventory_id = fields.Many2one(
        'stock.inventory.evaluation', 'Inventory', index=True,
        ondelete='cascade')
    product_id = fields.Many2one(
        'product.product', 'Product',
        domain=[('type', '=', 'product')],
        index=True, required=True)
    product_uom_id = fields.Many2one(
        'uom.uom', 'Product Unit of Measure',
        required=True)
    product_uom_category_id = fields.Many2one(string='Uom category',
                                              related='product_uom_id.category_id',
                                              readonly=True)
    product_qty = fields.Float(
        'Checked Quantity',
        digits=dp.get_precision('Product Unit of Measure'), default=0)
    location_id = fields.Many2one(
        'stock.location', 'Location',
        index=True, required=True)
    prod_lot_id = fields.Many2one(
        'stock.production.lot', 'Lot/Serial Number',
        domain="[('product_id','=',product_id)]")
    company_id = fields.Many2one(
        'res.company', 'Company', related='inventory_id.company_id',
        index=True, readonly=True, store=True)
    state = fields.Selection(
        'Status', related='inventory_id.state', readonly=True)
    theoretical_qty = fields.Float(
        'Theoretical Quantity', compute='_compute_theoretical_qty',
        digits=dp.get_precision('Product Unit of Measure'), readonly=True,
        store=True)
    inventory_location_id = fields.Many2one(
        'stock.location', 'Inventory Location',
        related='inventory_id.location_id', related_sudo=False, readonly=False)
    product_tracking = fields.Selection('Tracking',
                                        related='product_id.tracking',
                                        readonly=True)

    @api.one
    @api.depends('location_id', 'product_id', 'product_uom_id',
                 'company_id', 'prod_lot_id')
    def _compute_theoretical_qty(self):
        if not self.product_id:
            self.theoretical_qty = 0
            return
        theoretical_qty = self.product_id.get_theoretical_quantity(
            self.product_id.id,
            self.location_id.id,
            to_uom=self.product_uom_id.id,
        )
        self.theoretical_qty = theoretical_qty

    @api.onchange('product_id')
    def _onchange_product(self):
        res = {}
        # If no UoM or incorrect UoM put default one from product
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id
            res['domain'] = {'product_uom_id': [
                ('category_id', '=', self.product_id.uom_id.category_id.id)]}
        return res

    @api.onchange('product_id', 'location_id', 'product_uom_id', 'prod_lot_id')
    def _onchange_quantity_context(self):
        if self.product_id and self.location_id and self.product_id.uom_id.category_id == self.product_uom_id.category_id:  # TDE FIXME: last part added because crash
            self._compute_theoretical_qty()
            self.product_qty = self.theoretical_qty

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if 'product_id' in values and 'product_uom_id' not in values:
                values['product_uom_id'] = self.env['product.product'].browse(
                    values['product_id']).uom_id.id
        res = super(InventoryLine, self).create(vals_list)
        return res
