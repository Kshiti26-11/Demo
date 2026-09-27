from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class OrderStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ORDER_STATUS_UNSPECIFIED: _ClassVar[OrderStatus]
    ORDER_STATUS_AWAITING_PAYMENT: _ClassVar[OrderStatus]
    ORDER_STATUS_PAID: _ClassVar[OrderStatus]
    ORDER_STATUS_SHIPPED: _ClassVar[OrderStatus]
    ORDER_STATUS_CANCELLED: _ClassVar[OrderStatus]
ORDER_STATUS_UNSPECIFIED: OrderStatus
ORDER_STATUS_AWAITING_PAYMENT: OrderStatus
ORDER_STATUS_PAID: OrderStatus
ORDER_STATUS_SHIPPED: OrderStatus
ORDER_STATUS_CANCELLED: OrderStatus

class GetOrderSummaryRequest(_message.Message):
    __slots__ = ("order_id",)
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    def __init__(self, order_id: _Optional[str] = ...) -> None: ...

class Money(_message.Message):
    __slots__ = ("amount_minor", "currency")
    AMOUNT_MINOR_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_FIELD_NUMBER: _ClassVar[int]
    amount_minor: int
    currency: str
    def __init__(self, amount_minor: _Optional[int] = ..., currency: _Optional[str] = ...) -> None: ...

class Customer(_message.Message):
    __slots__ = ("customer_id", "display_name")
    CUSTOMER_ID_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
    customer_id: str
    display_name: str
    def __init__(self, customer_id: _Optional[str] = ..., display_name: _Optional[str] = ...) -> None: ...

class OrderSummary(_message.Message):
    __slots__ = ("order_id", "customer_name", "total_price", "status", "customer", "total", "shipping_eta")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    CUSTOMER_NAME_FIELD_NUMBER: _ClassVar[int]
    TOTAL_PRICE_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    CUSTOMER_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    SHIPPING_ETA_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    customer_name: str
    total_price: float
    status: OrderStatus
    customer: Customer
    total: Money
    shipping_eta: str
    def __init__(self, order_id: _Optional[str] = ..., customer_name: _Optional[str] = ..., total_price: _Optional[float] = ..., status: _Optional[_Union[OrderStatus, str]] = ..., customer: _Optional[_Union[Customer, _Mapping]] = ..., total: _Optional[_Union[Money, _Mapping]] = ..., shipping_eta: _Optional[str] = ...) -> None: ...
