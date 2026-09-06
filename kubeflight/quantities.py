from __future__ import annotations
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import re

class QuantityError(ValueError):
    """Raised when a Kubernetes resource quantity cannot be parsed."""

_Q = re.compile(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(n|u|m|k|K|M|G|T|P|E|Ki|Mi|Gi|Ti|Pi|Ei)?$")
_DEC = {
    "": Decimal(1), "n": Decimal("1e-9"), "u": Decimal("1e-6"), "m": Decimal("1e-3"),
    "k": Decimal("1e3"), "K": Decimal("1e3"), "M": Decimal("1e6"), "G": Decimal("1e9"),
    "T": Decimal("1e12"), "P": Decimal("1e15"), "E": Decimal("1e18"),
}
_BIN = {u: Decimal(1024) ** p for p, u in enumerate(("Ki","Mi","Gi","Ti","Pi","Ei"), start=1)}

def quantity(value: object | None, *, default: Decimal | None = Decimal(0)) -> Decimal:
    if value is None:
        if default is None:
            raise QuantityError("quantity is required")
        return default
    if isinstance(value, bool):
        raise QuantityError(f"invalid Kubernetes quantity: {value!r}")
    s = str(value).strip()
    m = _Q.fullmatch(s)
    if not m:
        raise QuantityError(f"invalid Kubernetes quantity: {s!r}")
    try:
        number = Decimal(m.group(1))
    except InvalidOperation as exc:
        raise QuantityError(f"invalid Kubernetes quantity: {s!r}") from exc
    suffix = m.group(2) or ""
    factor = _BIN.get(suffix, _DEC.get(suffix))
    if factor is None:
        raise QuantityError(f"unsupported Kubernetes quantity suffix: {suffix!r}")
    return number * factor

def cpu_millicores(value: object | None) -> int:
    # Kubernetes CPU is expressed in cores. Round fractional millicores upward so
    # unsupported precision can never make a workload look smaller than it is.
    cores = quantity(value)
    return int((cores * 1000).to_integral_value(rounding=ROUND_CEILING))

def memory_bytes(value: object | None) -> int:
    return int(quantity(value).to_integral_value(rounding=ROUND_CEILING))

def scalar_int(value: object | None) -> int:
    return int(quantity(value).to_integral_value(rounding=ROUND_CEILING))

def gib(value: object | None) -> float:
    return float(quantity(value) / (Decimal(1024) ** 3))
