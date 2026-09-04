import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Stores the FlowPilot bearer token in platform secure storage
/// (Keystore on Android, Keychain on iOS) — never SharedPreferences.
class SecureTokenStore {
  static const _tokenKey = 'flowpilot_access_token';

  final FlutterSecureStorage _storage = const FlutterSecureStorage();

  Future<void> save(String token) => _storage.write(key: _tokenKey, value: token);

  Future<String?> read() => _storage.read(key: _tokenKey);

  Future<void> clear() => _storage.delete(key: _tokenKey);
}
