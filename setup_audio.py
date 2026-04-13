#!/usr/bin/python3
audio_services = ["pipewire.service", "pipewire-pulse.service", "wireplumber.service"]
required_services = ["fm95.service"]
optional_services = ["chimer95.service", "rds95.service", "player.service", "stream.service"]

required_services_units = []
optional_services_units = []

import pulsectl, warnings
from pystemd.systemd1 import Unit
from pystemd.dbuslib import DBus
from dataclasses import dataclass

user_bus = DBus(user_mode=True).__enter__()
system_bus = DBus(user_mode=False).__enter__()

print("Restarting the audio server...")
for service in audio_services: Unit(external_id=service.removesuffix("_system").encode(), bus=system_bus if service.endswith("_system") else user_bus, _autoload=True).Unit.Restart(b"replace")

pulse = pulsectl.Pulse()

for service in required_services:
        ser = Unit(external_id=service.removesuffix("_system").encode(), bus=system_bus if service.endswith("_system") else user_bus, _autoload=True)
        if ser.Unit.Description == ser.Unit.Id: raise Exception(f"{service} not installed")
        required_services_units.append(ser)
for service in optional_services:
        ser = Unit(external_id=service.removesuffix("_system").encode(), bus=system_bus if service.endswith("_system") else user_bus, _autoload=True)
        if ser.Unit.Description == ser.Unit.Id:
                warnings.warn(f"{service} not installed")
                optional_services_units.append(None)
                continue
        optional_services_units.append(ser)

for service in required_services_units + optional_services_units:
        if service is not None: service.Unit.Stop(b"replace")

RATE = 48000

@dataclass
class SC4_Settings:
        rmsPeak: float
        attack: float
        release: float
        threshold: float
        ratio: int
        knee: float
        makeup: float
        module: str = "module-ladspa-sink"
        module_args: str = "plugin=sc4_1882 label=sc4"
        def __str__(self) -> str:
                return f"{self.module_args} control={self.rmsPeak},{self.attack},{self.release},{self.threshold},{self.ratio},{self.knee},{self.makeup}"

@dataclass
class FilterChain:
        filters: list[SC4_Settings]

def get_null_sinks(filters, base): return ["real_"*i + base for i in range(len(filters)+1)]

def load_null_sink(name: str, args:str = "", rate: int = RATE): pulse.module_load("module-null-sink", f"sink_name={name} rate={rate} {args}")

def load_filter_chain(filters: FilterChain):
        ns = get_null_sinks(filters.filters, "radio_broadcast")
        load_null_sink(ns.pop())

        ns.reverse()
        for i,j in zip(filters.filters, ns):
                pulse.module_load(i.module, f"rate={RATE} sink_name={j} sink_master={'real_' + j} {str(i)}")
        sink_name = "radio_broadcast"
        sink_obj = next((s for s in pulse.sink_list() if s.name == sink_name), None)
        if sink_obj:
            pulse.default_set(sink_obj)
        else:
            print(f"Sink {sink_name} not found!")


filter_chain = FilterChain(
        [
                SC4_Settings(
                        rmsPeak=0.25,
                        attack=10,
                        release=80,
                        threshold=-6,
                        ratio=12,
                        knee=6,
                        makeup=12
                ),
                SC4_Settings(
                        rmsPeak=0.75,
                        attack=5,
                        release=150,
                        threshold=-12,
                        ratio=6,
                        knee=3,
                        makeup=12
                )
        ]
)

load_filter_chain(filter_chain)

load_null_sink("FM_Audio")
pulse.module_load("module-loopback", f"sink=FM_Audio source={get_null_sinks(filter_chain.filters, 'radio_broadcast')[-1]}.monitor rate={RATE}")

load_null_sink("Online_Audio")
pulse.module_load("module-loopback", f"sink=Online_Audio source=FM_Audio.monitor")

sinks = pulse.sink_list()
online_audio_sink = None
for sink in sinks:
    if sink.name == "Online_Audio":
        online_audio_sink = sink
        break
pulse.volume_set_all_chans(online_audio_sink, 0.5)

load_null_sink("FM_MPX", "channels=1", 192000)
load_null_sink("RDS", "channels=4", 4750)
pulse.module_load("module-native-protocol-tcp", "auth-anonymous=true")

for service in required_services_units + optional_services_units:
        if service is not None: service.Unit.Start(b"replace")