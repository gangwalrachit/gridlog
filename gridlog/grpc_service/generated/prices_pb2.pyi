import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PriceWindowRequest(_message.Message):
    __slots__ = ("zone", "start", "end")
    ZONE_FIELD_NUMBER: _ClassVar[int]
    START_FIELD_NUMBER: _ClassVar[int]
    END_FIELD_NUMBER: _ClassVar[int]
    zone: str
    start: _timestamp_pb2.Timestamp
    end: _timestamp_pb2.Timestamp
    def __init__(self, zone: _Optional[str] = ..., start: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., end: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class AsOfRequest(_message.Message):
    __slots__ = ("zone", "start", "end", "as_of")
    ZONE_FIELD_NUMBER: _ClassVar[int]
    START_FIELD_NUMBER: _ClassVar[int]
    END_FIELD_NUMBER: _ClassVar[int]
    AS_OF_FIELD_NUMBER: _ClassVar[int]
    zone: str
    start: _timestamp_pb2.Timestamp
    end: _timestamp_pb2.Timestamp
    as_of: _timestamp_pb2.Timestamp
    def __init__(self, zone: _Optional[str] = ..., start: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., end: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., as_of: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class PriceRow(_message.Message):
    __slots__ = ("valid_time", "value")
    VALID_TIME_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    valid_time: _timestamp_pb2.Timestamp
    value: float
    def __init__(self, valid_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., value: _Optional[float] = ...) -> None: ...

class PriceResponse(_message.Message):
    __slots__ = ("rows",)
    ROWS_FIELD_NUMBER: _ClassVar[int]
    rows: _containers.RepeatedCompositeFieldContainer[PriceRow]
    def __init__(self, rows: _Optional[_Iterable[_Union[PriceRow, _Mapping]]] = ...) -> None: ...

class RevisionRow(_message.Message):
    __slots__ = ("valid_time", "knowledge_time", "value")
    VALID_TIME_FIELD_NUMBER: _ClassVar[int]
    KNOWLEDGE_TIME_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    valid_time: _timestamp_pb2.Timestamp
    knowledge_time: _timestamp_pb2.Timestamp
    value: float
    def __init__(self, valid_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., knowledge_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., value: _Optional[float] = ...) -> None: ...

class RevisionResponse(_message.Message):
    __slots__ = ("rows",)
    ROWS_FIELD_NUMBER: _ClassVar[int]
    rows: _containers.RepeatedCompositeFieldContainer[RevisionRow]
    def __init__(self, rows: _Optional[_Iterable[_Union[RevisionRow, _Mapping]]] = ...) -> None: ...
