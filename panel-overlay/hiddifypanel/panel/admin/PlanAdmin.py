from apiflask import abort
from flask import g, request
from flask_admin.actions import action
from flask_admin.contrib.sqla import tools
from flask_babel import gettext as __
from flask_babel import lazy_gettext as _
from wtforms.validators import NumberRange

from hiddifypanel.auth import login_required
from hiddifypanel.models import AdminUser, CommercialPlan, PaymentProvider, PlanCycle, Role, UserMode
from hiddifypanel.panel import custom_widgets

from .adminlte import AdminLTEModelView


class PlanAdmin(AdminLTEModelView):
    column_default_sort = ("sort_order", False)
    column_list = [
        "name",
        "enable",
        "is_public",
        "price",
        "currency",
        "payment_provider",
        "cycle",
        "usage_limit",
        "package_days",
        "max_ips",
        "mode",
    ]
    column_searchable_list = ["name", "note"]
    column_sortable_list = ["name", "sort_order", "price", "package_days", "max_ips"]
    column_editable_list = ["name", "price", "note", "sort_order", "enable", "is_public"]
    form_columns = [
        "name",
        "enable",
        "is_public",
        "sort_order",
        "price",
        "currency",
        "payment_provider",
        "cycle",
        "usage_limit",
        "package_days",
        "max_ips",
        "mode",
        "note",
    ]
    form_overrides = {
        "usage_limit": custom_widgets.UsageField,
        "cycle": custom_widgets.EnumSelectField,
        "mode": custom_widgets.EnumSelectField,
        "payment_provider": custom_widgets.EnumSelectField,
    }
    form_widget_args = {
        "usage_limit": {"min": "0"},
        "package_days": {"min": "1"},
        "max_ips": {"min": "1", "max": "10"},
        "price": {"min": "0"},
        "sort_order": {"min": "0"},
    }
    form_args = {
        "cycle": {"enum": PlanCycle},
        "mode": {"enum": UserMode},
        "payment_provider": {"enum": PaymentProvider},
        "package_days": {"validators": [NumberRange(min=1, max=36500)]},
        "max_ips": {"validators": [NumberRange(min=1, max=10)]},
        "price": {"validators": [NumberRange(min=0, max=1000000000)]},
    }
    column_labels = {
        "name": _("Plan"),
        "enable": _("Enable"),
        "is_public": _("Public"),
        "price": _("Price"),
        "currency": _("Currency"),
        "payment_provider": _("Payment Provider"),
        "cycle": _("Cycle"),
        "usage_limit": _("user.usage_limit_GB"),
        "package_days": _("Package Days"),
        "max_ips": _("Max IPs"),
        "mode": _("Mode"),
        "sort_order": _("Sort Order"),
        "note": _("Note"),
    }
    column_formatters = {
        "usage_limit": lambda v, c, m, p: f"{int(m.usage_limit_GB) if float(m.usage_limit_GB).is_integer() else m.usage_limit_GB:g} GB",
    }

    column_descriptions = {
        "price": _("Price for future billing integrations. YooKassa will be connected later."),
        "payment_provider": _("Prepared for future payment automation."),
        "max_ips": _("How many simultaneous IPs or connections this tariff allows."),
    }

    def search_placeholder(self):
        return f"{__('search')} {__('Plan')} {__('Note')}"

    def is_accessible(self):
        if login_required(roles={Role.super_admin, Role.admin})(lambda: True)() != True:
            return False
        return True

    def on_model_change(self, form, model, is_created):
        model.max_ips = max(1, min(int(model.max_ips or 1), 10))
        model.package_days = max(1, min(int(model.package_days or 1), 36500))
        model.price = max(0, int(model.price or 0))
        model.sort_order = max(0, int(model.sort_order or 0))
        if not model.added_by:
            model.added_by = g.account.id

    def get_query(self):
        query = super().get_query()
        admin_id = int(request.args.get("admin_id") or g.account.id)
        if admin_id not in g.account.recursive_sub_admins_ids():
            abort(403)
        admin = AdminUser.query.filter(AdminUser.id == admin_id).first()
        if not admin:
            abort(403)
        return query.filter(CommercialPlan.added_by.in_(admin.recursive_sub_admins_ids()))

    def get_count_query(self):
        query = super().get_count_query()
        admin_id = int(request.args.get("admin_id") or g.account.id)
        if admin_id not in g.account.recursive_sub_admins_ids():
            abort(403)
        admin = AdminUser.query.filter(AdminUser.id == admin_id).first()
        if not admin:
            abort(403)
        return query.filter(CommercialPlan.added_by.in_(admin.recursive_sub_admins_ids()))

    @action("disable_plans", "Disable", "Are you sure you want to disable selected plans?")
    def action_disable(self, ids):
        query = tools.get_query_for_ids(self.get_query(), self.model, ids)
        count = query.update({"enable": False})
        self.session.commit()
        from hiddifypanel import hutils
        hutils.flask.flash(_("%(count)s plans were successfully disabled.", count=count), "success")

    @action("enable_plans", "Enable", "Are you sure you want to enable selected plans?")
    def action_enable(self, ids):
        query = tools.get_query_for_ids(self.get_query(), self.model, ids)
        count = query.update({"enable": True})
        self.session.commit()
        from hiddifypanel import hutils
        hutils.flask.flash(_("%(count)s plans were successfully enabled.", count=count), "success")
