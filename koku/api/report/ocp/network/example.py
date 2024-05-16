import dataclasses
import secrets
from datetime import datetime
from datetime import timedelta


def get_random_usage_amount(min: int = 1, length: int = 10) -> float:
    return secrets.choice(range(min, 10**length - 1)) / (10 ** (length - 1))


def zero_usd() -> "Value":
    return Value(0.0, units="USD")


def zero_gb() -> "Value":
    return Value(0.0, units="GB")


@dataclasses.dataclass(frozen=True)
class Value:
    value: float = dataclasses.field(default_factory=get_random_usage_amount)
    units: str = "GB"

    def __add__(self, other):
        if isinstance(other, self.__class__):
            return self.__class__(self.value + other.value, self.units)

        return self.__class__(self.value + other, self.units)

    def __sub__(self, other):
        if isinstance(other, self.__class__):
            return self.__class__(self.value - other.value, self.units)

        return self.__class__(self.value - other, self.units)


@dataclasses.dataclass
class Cost:
    raw: Value = dataclasses.field(default_factory=zero_usd)
    markup: Value = dataclasses.field(default_factory=zero_usd)
    usage: Value = dataclasses.field(default_factory=zero_usd)
    total: Value = dataclasses.field(init=False)

    def __post_init__(self):
        self.total = Value(sum((self.raw.value, self.markup.value, self.usage.value)), units="USD")


@dataclasses.dataclass
class NetworkUsage:
    date: str = datetime.now().strftime("%Y-%m-%d")
    data_transfer_in: Value = dataclasses.field(default_factory=Value)
    data_transfer_out: Value = dataclasses.field(default_factory=Value)
    resource_id: str = "i-727f8dc9c567f1552"
    clusters: list[str] = dataclasses.field(default_factory=list)
    source_uuid: str = "6795d5e6-951c-4382-a8d3-390515d7ec3d"
    region: str = "us-east-2"
    infrastructure: Cost = dataclasses.field(init=False)
    supplementary: Cost = dataclasses.field(init=False, default_factory=Cost)
    markup: Cost = dataclasses.field(init=False)

    def __post_init__(self):
        amount = get_random_usage_amount()
        self.infrastructure = Cost(Value(amount, units="USD"))
        self.markup = self.infrastructure

        if not self.clusters:
            self.clusters = ["Test AWS Cluster"]


@dataclasses.dataclass
class DailyNetworkUsage:
    date: str
    values: list[NetworkUsage]


@dataclasses.dataclass
class Total:
    usage: Value = Value()
    data_transfer_in: Value = Value()
    data_transfer_out: Value = Value()
    infrastructure: Cost = dataclasses.field(default_factory=Cost)
    supplementary: Cost = dataclasses.field(default_factory=Cost)
    cost: Cost = dataclasses.field(default_factory=Cost)

    @classmethod
    def generate(cls, data: list[DailyNetworkUsage]) -> "Total":
        data_transfer_in = cls.total_value("data_transfer_in", data)
        data_transfer_out = cls.total_value("data_transfer_out", data)

        return cls(
            usage=Value(data_transfer_in + data_transfer_out),
            data_transfer_in=Value(data_transfer_in),
            data_transfer_out=Value(data_transfer_out),
            infrastructure=cls.total_cost("infrastructure", data),
            supplementary=cls.total_cost("supplementary", data),
            cost=cls.total_cost("infrastructure", data),
        )

    @staticmethod
    def total_value(field: str, data: list[DailyNetworkUsage]) -> float:
        return sum(getattr(network_usage, field).value for daily_usage in data for network_usage in daily_usage.values)

    @staticmethod
    def total_cost(field: str, data: list[DailyNetworkUsage]) -> Cost:
        cost_fields = (item.name for item in dataclasses.fields(Cost))
        total = Cost()
        for cost_field in cost_fields:
            for daily_usage in data:
                for network_usage in daily_usage.values:
                    running_total_value = getattr(total, cost_field)
                    value_to_add = getattr(getattr(network_usage, field), cost_field)
                    setattr(total, cost_field, running_total_value + value_to_add)

        return total


@dataclasses.dataclass
class ExampleResponseBody:
    total: Total
    data: list[DailyNetworkUsage]

    @classmethod
    def generate(cls, count=10, *args, **kwargs):
        daily_usage = []
        date_counter = datetime.today()
        for _ in range(count):
            date = date_counter.strftime("%Y-%m-%d")
            daily_usage.append(DailyNetworkUsage(date, [NetworkUsage(date)]))
            date_counter -= timedelta(days=1)

        return cls(Total.generate(daily_usage), daily_usage)


@dataclasses.dataclass
class TotalGroupBy(Total):
    @staticmethod
    def total_value(field: str, data: list["GroupByDailyNetworkUsage"]) -> float:
        return sum(
            getattr(network_usage, field).value
            for daily_usage in data
            for cluster in daily_usage.clusters
            for network_usage in cluster.values
        )

    @staticmethod
    def total_cost(field: str, data: list["GroupByDailyNetworkUsage"]) -> Cost:
        cost_fields = (item.name for item in dataclasses.fields(Cost))
        total = Cost()
        for cost_field in cost_fields:
            for daily_usage in data:
                for cluster in daily_usage.clusters:
                    for network_usage in cluster.values:
                        running_total_value = getattr(total, cost_field)
                        value_to_add = getattr(getattr(network_usage, field), cost_field)
                        setattr(total, cost_field, running_total_value + value_to_add)

        return total


@dataclasses.dataclass
class GroupByNetworkUsage:
    cluster: str = "test-ocp-cluster"
    values: list[NetworkUsage] = dataclasses.field(default_factory=list)

    def __post_init__(self):
        for value in self.values:
            value.cluster = self.cluster


@dataclasses.dataclass
class GroupByDailyNetworkUsage:
    date: str
    clusters: list[GroupByNetworkUsage]


@dataclasses.dataclass
class ExampleGroupByResponseBody:
    total: Total
    data: list[GroupByDailyNetworkUsage]

    @classmethod
    def generate(cls, count=10, *args, **kwargs):
        daily_usage = []
        date_counter = datetime.today()
        for _ in range(count):
            date = date_counter.strftime("%Y-%m-%d")
            daily_usage.append(GroupByDailyNetworkUsage(date, [GroupByNetworkUsage(values=[NetworkUsage(date)])]))
            date_counter -= timedelta(days=1)

        return cls(TotalGroupBy.generate(daily_usage), daily_usage)
