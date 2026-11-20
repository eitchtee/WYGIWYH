from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Iterable

from django.core.exceptions import ValidationError
from django.utils.formats import number_format
from django.utils.translation import gettext_lazy as _

from apps.splits.models import SplitExpense, SplitExpenseShare, SplitParticipant


@dataclass(frozen=True)
class ComputedShare:
    participant: SplitParticipant
    amount: Decimal
    percentage: Decimal | None = None
    shares: Decimal | None = None


def quantize_unit(decimal_places: int) -> Decimal:
    places = max(0, min(int(decimal_places), 6))
    return Decimal("1").scaleb(-places)


def _distribute_remainder(
    total: Decimal,
    raw_amounts: list[Decimal],
    unit: Decimal,
) -> list[Decimal]:
    """Quantize each raw amount down to `unit` and distribute leftover units
    by largest fractional remainder (Hamilton / largest-remainder method).
    Guarantees sum(result) == total quantized to `unit`.
    """
    quantized_total = total.quantize(unit, rounding=ROUND_HALF_UP)
    floored = [amt.quantize(unit, rounding=ROUND_DOWN) for amt in raw_amounts]
    remainder = quantized_total - sum(floored, Decimal("0"))
    if remainder == 0:
        return floored

    steps = int((remainder / unit).to_integral_value(rounding=ROUND_HALF_UP))
    step_sign = unit if steps > 0 else -unit
    steps = abs(steps)

    # Order indices by largest fractional remainder (tie-break by original index)
    remainders = [
        (raw - flr, -idx, idx)
        for idx, (raw, flr) in enumerate(zip(raw_amounts, floored))
    ]
    remainders.sort(reverse=True)

    result = list(floored)
    for i in range(steps):
        target_idx = remainders[i % len(remainders)][2]
        result[target_idx] += step_sign
    return result


def compute_expense_shares(
    *,
    total_amount: Decimal,
    split_type: str,
    participants: Iterable[SplitParticipant],
    decimal_places: int = 2,
    values_by_participant_id: dict[int, Decimal] | None = None,
) -> list[ComputedShare]:
    """Compute exact, penny-balanced shares for a SplitExpense.

    `values_by_participant_id` maps participant.id -> Decimal:
      - EQUAL: ignored (all provided participants split equally)
      - EXACT: exact amount per participant
      - PERCENTAGE: percentage (0..100) per participant, must sum to 100
      - SHARES: positive share weight per participant
    """
    participant_list = list(participants)
    if not participant_list:
        raise ValidationError(_("Select at least one participant for this expense."))

    unit = quantize_unit(decimal_places)
    total = Decimal(total_amount).quantize(unit, rounding=ROUND_HALF_UP)
    if total <= 0:
        raise ValidationError(_("Expense amount must be greater than zero."))

    values = values_by_participant_id or {}

    if split_type == SplitExpense.SplitType.EQUAL:
        count = Decimal(len(participant_list))
        raw = [total / count for _ in participant_list]
        amounts = _distribute_remainder(total, raw, unit)
        return [
            ComputedShare(participant=p, amount=amt)
            for p, amt in zip(participant_list, amounts)
        ]

    if split_type == SplitExpense.SplitType.EXACT:
        amounts: list[Decimal] = []
        for p in participant_list:
            val = values.get(p.id, Decimal("0"))
            if val < 0:
                raise ValidationError(
                    _("Exact amount for %(name)s cannot be negative.")
                    % {"name": p.name}
                )
            amounts.append(Decimal(val).quantize(unit, rounding=ROUND_HALF_UP))
        total_entered = sum(amounts, Decimal("0"))
        if total_entered != total:
            raise ValidationError(
                _(
                    "Exact amounts sum to %(entered)s, but the expense total is %(total)s."
                )
                % {"entered": number_format(total_entered), "total": number_format(total)}
            )
        return [
            ComputedShare(participant=p, amount=amt)
            for p, amt in zip(participant_list, amounts)
        ]

    if split_type == SplitExpense.SplitType.PERCENTAGE:
        percentages: list[Decimal] = []
        for p in participant_list:
            pct = values.get(p.id, Decimal("0"))
            if pct < 0:
                raise ValidationError(
                    _("Percentage for %(name)s cannot be negative.")
                    % {"name": p.name}
                )
            percentages.append(Decimal(pct))
        pct_sum = sum(percentages, Decimal("0"))
        if abs(pct_sum - Decimal("100")) > Decimal("0.01"):
            raise ValidationError(
                _("Percentages must sum to 100%% (currently %(sum)s%%).")
                % {"sum": number_format(pct_sum)}
            )
        raw = [total * (pct / Decimal("100")) for pct in percentages]
        amounts = _distribute_remainder(total, raw, unit)
        return [
            ComputedShare(
                participant=p,
                amount=amt,
                percentage=pct.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
            )
            for p, amt, pct in zip(participant_list, amounts, percentages)
        ]

    if split_type == SplitExpense.SplitType.SHARES:
        share_weights: list[Decimal] = []
        for p in participant_list:
            w = values.get(p.id, Decimal("0"))
            if w < 0:
                raise ValidationError(
                    _("Shares for %(name)s cannot be negative.") % {"name": p.name}
                )
            share_weights.append(Decimal(w))
        weight_sum = sum(share_weights, Decimal("0"))
        if weight_sum <= 0:
            raise ValidationError(_("Total shares must be greater than zero."))
        raw = [total * (w / weight_sum) for w in share_weights]
        amounts = _distribute_remainder(total, raw, unit)
        return [
            ComputedShare(
                participant=p,
                amount=amt,
                shares=w.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
            )
            for p, amt, w in zip(participant_list, amounts, share_weights)
        ]

    raise ValidationError(_("Unsupported split type: %(type)s") % {"type": split_type})


def replace_expense_shares(expense: SplitExpense, computed: list[ComputedShare]):
    expense.shares.all().delete()
    SplitExpenseShare.objects.bulk_create(
        [
            SplitExpenseShare(
                expense=expense,
                participant=cs.participant,
                amount=cs.amount,
                percentage=cs.percentage,
                shares=cs.shares,
            )
            for cs in computed
        ]
    )
