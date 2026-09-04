import 'package:flutter_dotenv/flutter_dotenv.dart';

/// Central place for environment-driven config. Never hard-code the base
/// URL anywhere else — read it from here so switching between the Android
/// emulator, iOS simulator, and a physical device is a one-line .env change.
class Environment {
  static String get baseUrl =>
      dotenv.env['API_BASE_URL'] ?? 'http://10.0.2.2:8000';
}
