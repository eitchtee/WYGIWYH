from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum

from apps.splits.models import (
    SplitEvent,
    SplitExpense,
    SplitExpenseShare,
    SplitParticipant,
    SplitPayment,
)
from apps.splits.services.splitting import quantize_unit


@dataclass(frozen=True)
class ParticipantBalance:
    participant: SplitParticipant
    total_paid: Decimal
    total_owed: Decimal
    payments_sent: Decimal
    payments_received: Decimal
    net_balance: Decimal  # > 0 means others owe this participant; < 0 means this participant owes others


@dataclass(frozen=True)
class SettlementTransfer:
    from_participant: SplitParticipant
    to_participant: SplitParticipant
    amount: Decimal


def calculate_event_balances(event: SplitEvent) -> list[ParticipantBalance]:
    """Compute exact per-participant balances for an event.

    net_balance = total_paid - total_owed + payments_sent - payments_received
      > 0 => participant is owed money (creditor)
      < 0 => participant owes money (debtor)
      = 0 => settled
    """
    unit = quantize_unit(event.currency.decimal_places)
    zero = Decimal("0").quantize(unit)

    participants = list(event.participants.all().order_by("-is_active", "name", "id"))
    if not participants:
        return []

    paid_map = {
        row["paid_by_id"]: row["total"] or zero
        for row in SplitExpense.objects.filter(event=event)
        .values("paid_by_id")
        .annotate(total=Sum("amount"))
    }
    owed_map = {
        row["participant_id"]: row["total"] or zero
        for row in SplitExpenseShare.objects.filter(expense__event=event)
        .values("participant_id")
        .annotate(total=Sum("amount"))
    }
    sent_map = {
        row["from_participant_id"]: row["total"] or zero
        for row in SplitPayment.objects.filter(event=event)
        .values("from_participant_id")
        .annotate(total=Sum("amount"))
    }
    received_map = {
        row["to_participant_id"]: row["total"] or zero
        for row in SplitPayment.objects.filter(event=event)
        .values("to_participant_id")
        .annotate(total=Sum("amount"))
    }

    balances: list[ParticipantBalance] = []
    for p in participants:
        paid = paid_map.get(p.id, zero).quantize(unit, rounding=ROUND_HALF_UP)
        owed = owed_map.get(p.id, zero).quantize(unit, rounding=ROUND_HALF_UP)
        sent = sent_map.get(p.id, zero).quantize(unit, rounding=ROUND_HALF_UP)
        received = received_map.get(p.id, zero).quantize(unit, rounding=ROUND_HALF_UP)
        net = (paid - owed + sent - received).quantize(unit, rounding=ROUND_HALF_UP)
        balances.append(
            ParticipantBalance(
                participant=p,
                total_paid=paid,
                total_owed=owed,
                payments_sent=sent,
                payments_received=received,
                net_balance=net,
            )
        )
    return balances


def simplify_debts(
    balances: list[ParticipantBalance],
    decimal_places: int = 2,
) -> list[SettlementTransfer]:
    """Find a minimal-roundtrip set of settlement transfers.

    Strategy:
      1. Drop zero-balance participants.
      2. Eliminate exact 1-to-1 debtor/creditor matches first (each removes 2
         participants in 1 transfer — strictly optimal).
      3. For small remaining groups (<= 14 non-zero participants), find the
         maximum number of disjoint zero-sum subsets via DP/bitmask to achieve
         the provably minimum number of transfers (N - K transfers for K subsets).
      4. Within each zero-sum subset (or for larger groups directly), greedily
         match largest debtor to largest creditor so there are zero roundtrips.
    """
    unit = quantize_unit(decimal_places)
    zero = Decimal("0").quantize(unit)

    # Map to integer minor units for exact subset-sum math
    scale = int(Decimal("1") / unit)

    debtors: list[list] = []  # [participant, int_amount_owed]
    creditors: list[list] = []  # [participant, int_amount_owed_to_them]

    for b in balances:
        val = int((b.net_balance * scale).to_integral_value(rounding=ROUND_HALF_UP))
        if val < 0:
            debtors.append([b.participant, -val])
        elif val > 0:
            creditors.append([b.participant, val])

    transfers: list[SettlementTransfer] = []

    # Step 1: Exact 1-to-1 matches (strictly optimal)
    remaining_debtors: list[list] = []
    for d in debtors:
        matched_idx = next(
            (i for i, c in enumerate(creditors) if c[1] == d[1]),
            None,
        )
        if matched_idx is not None:
            c = creditors.pop(matched_idx)
            transfers.append(
                SettlementTransfer(
                    from_participant=d[0],
                    to_participant=c[0],
                    amount=(Decimal(d[1]) * unit).quantize(unit),
                )
            )
        else:
            remaining_debtors.append(d)

    debtors = remaining_debtors

    # Combine remaining signed items for subset decomposition
    items: list[tuple[SplitParticipant, int]] = [
        (d[0], -d[1]) for d in debtors
    ] + [(c[0], c[1]) for c in creditors]

    if not items:
        return transfers

    def _greedy_settle(subset: list[tuple[SplitParticipant, int]]) -> list[SettlementTransfer]:
        sub_debtors = sorted(
            [[p, -amt] for p, amt in subset if amt < 0],
            key=lambda x: (-x[1], x[0].id),
        )
        sub_creditors = sorted(
            [[p, amt] for p, amt in subset if amt > 0],
            key=lambda x: (-x[1], x[0].id),
        )
        out: list[SettlementTransfer] = []
        i = j = 0
        while i < len(sub_debtors) and j < len(sub_creditors):
            d = sub_debtors[i]
            c = sub_creditors[j]
            pay = min(d[1], c[1])
            if pay > 0:
                out.append(
                    SettlementTransfer(
                        from_participant=d[0],
                        to_participant=c[0],
                        amount=(Decimal(pay) * unit).quantize(unit),
                    )
                )
                d[1] -= pay
                c[1] -= pay
            if d[1] == 0:
                i += 1
            if c[1] == 0:
                j += 1
        return out

    # Step 2: Optimal zero-sum subset partition for <= 14 remaining participants
    n = len(items)
    if 3 <= n <= 14:
        full_mask = (1 << n) - 1
        subset_sum = [0] * (1 << n)
        for mask in range(1, 1 << n):
            lsb = mask & -mask
            idx = lsb.bit_length() - 1
            subset_sum[mask] = subset_sum[mask ^ lsb] + items[idx][1]

        # dp[mask] = max number of disjoint non-empty zero-sum subsets partitioning mask
        dp = [-1] * (1 << n)
        parent = [0] * (1 << n)
        dp[0] = 0

        zero_masks = [m for m in range(1, 1 << n) if subset_sum[m] == 0]
        # Minimal zero-sum subsets (no proper non-empty zero-sum submask)
        for mask in zero_masks:
            best = 1
            best_sub = mask
            sub = (mask - 1) & mask
            while sub > 0:
                if subset_sum[sub] == 0 and dp[mask ^ sub] > 0:
                    cand = dp[sub] + dp[mask ^ sub]
                    if cand > best:
                        best = cand
                        best_sub = sub
                sub = (sub - 1) & mask
            dp[mask] = best
            parent[mask] = best_sub

        if dp[full_mask] > 0:
            # Reconstruct disjoint zero-sum subsets
            partitions: list[int] = []
            stack = [full_mask]
            while stack:
                m = stack.pop()
                sub = parent[m]
                if sub == m:
                    partitions.append(m)
                else:
                    stack.append(sub)
                    stack.append(m ^ sub)

            for part_mask in partitions:
                subset = [items[i] for i in range(n) if part_mask & (1 << i)]
                transfers.extend(_greedy_settle(subset))
        else:
            transfers.extend(_greedy_settle(items))
    else:
        transfers.extend(_greedy_settle(items))

    # Deterministic display order: largest transfer first, then names
    transfers.sort(
        key=lambda t: (-t.amount, t.from_participant.name.lower(), t.to_participant.name.lower())
    )
    return transfers


def get_event_settlement_summary(event: SplitEvent) -> dict:
    balances = calculate_event_balances(event)
    transfers = simplify_debts(balances, decimal_places=event.currency.decimal_places)
    total_spent = sum(
        (b.total_paid for b in balances),
        Decimal("0").quantize(quantize_unit(event.currency.decimal_places)),
    )
    return {
        "balances": balances,
        "balances_by_id": {b.participant.id: b for b in balances},
        "transfers": transfers,
        "total_spent": total_spent,
    }
