/**
 * Decentlab DL-IAM (Indoor Ambiance Monitor) payload decoder for ChirpStack.
 * Source: https://github.com/decentlab/decentlab-decoders (DL-IAM)
 *
 * DL-IAM measures: CO2, VOC, temperature, humidity, barometric pressure,
 * ambient light, and motion/presence (activity counter).
 *
 * ChirpStack expects: Decode(fPort, bytes, variables) -> object
 */
function Decode(fPort, bytes, variables) {
  if (!bytes || bytes.length < 5) {
    return { error: "payload too short" };
  }

  var decentlab_decoder = {
    PROTOCOL_VERSION: 2,
    SENSORS: [
      { length: 1, values: [{ name: "battery_voltage", displayName: "Battery voltage", convert: function (x) { return x[0] / 1000; }, unit: "V" }] },
      { length: 2, values: [{ name: "air_temperature", displayName: "Air temperature", convert: function (x) { return 175 * x[0] / 65535 - 45; }, unit: "°C" }, { name: "air_humidity", displayName: "Air humidity", convert: function (x) { return 100 * x[1] / 65535; }, unit: "%" }] },
      { length: 1, values: [{ name: "barometric_pressure", displayName: "Barometric pressure", convert: function (x) { return x[0] * 2; }, unit: "Pa" }] },
      { length: 2, values: [{ name: "ambient_light_visible_infrared", displayName: "Ambient light (visible + infrared)", convert: function (x) { return x[0]; } }, { name: "ambient_light_infrared", displayName: "Ambient light (infrared)", convert: function (x) { return x[1]; } }, { name: "illuminance", displayName: "Illuminance", convert: function (x) { return Math.max(Math.max(1.0 * x[0] - 1.64 * x[1], 0.59 * x[0] - 0.86 * x[1]), 0) * 1.5504; }, unit: "lx" }] },
      { length: 3, values: [{ name: "co2_concentration", displayName: "CO2 concentration", convert: function (x) { return x[0] - 32768; }, unit: "ppm" }, { name: "co2_sensor_status", displayName: "CO2 sensor status", convert: function (x) { return x[1]; } }, { name: "raw_ir_reading", displayName: "Raw IR reading", convert: function (x) { return x[2]; } }] },
      { length: 1, values: [{ name: "activity_counter", displayName: "Activity counter", convert: function (x) { return x[0]; } }] },
      { length: 1, values: [{ name: "total_voc", displayName: "Total VOC", convert: function (x) { return x[0]; }, unit: "ppb" }] }
    ],
    read_int: function (bytes, pos) {
      return (bytes[pos] << 8) + bytes[pos + 1];
    },
    decode: function (bytes) {
      var i, j;
      var version = bytes[0];
      if (version !== this.PROTOCOL_VERSION) {
        return { error: "protocol version " + version + " doesn't match v2" };
      }
      var deviceId = this.read_int(bytes, 1);
      var flags = this.read_int(bytes, 3);
      var result = { protocol_version: version, device_id: deviceId };
      var pos = 5;
      for (i = 0; i < this.SENSORS.length; i++, flags >>= 1) {
        if ((flags & 1) !== 1) continue;
        var sensor = this.SENSORS[i];
        var x = [];
        for (j = 0; j < sensor.length; j++) {
          x.push(this.read_int(bytes, pos));
          pos += 2;
        }
        for (j = 0; j < sensor.values.length; j++) {
          var value = sensor.values[j];
          if ("convert" in value) {
            result[value.name] = value.convert.bind(this)(x);
          }
        }
      }
      return result;
    }
  };

  var b = Array.isArray(bytes) ? bytes : Array.from(bytes);
  return decentlab_decoder.decode(b);
}
