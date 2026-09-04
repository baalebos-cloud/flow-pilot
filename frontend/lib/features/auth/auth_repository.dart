import '../../core/api_client.dart';
import '../../core/secure_token_store.dart';

class AuthRepository {
  AuthRepository({ApiClient? apiClient, SecureTokenStore? tokenStore})
      : _api = apiClient ?? ApiClient(),
        _tokenStore = tokenStore ?? SecureTokenStore();

  final ApiClient _api;
  final SecureTokenStore _tokenStore;

  Future<void> register({
    required String email,
    required String name,
    required String password,
  }) async {
    final response = await _api.post('/v1/auth/register', data: {
      'email': email,
      'name': name,
      'password': password,
    });
    await _tokenStore.save(response['access_token'] as String);
  }

  Future<void> login({required String email, required String password}) async {
    final response = await _api.post('/v1/auth/login', data: {
      'email': email,
      'password': password,
    });
    await _tokenStore.save(response['access_token'] as String);
  }

  /// Called on app start. Returns the current user map if a stored token
  /// is still valid, otherwise clears it and returns null.
  Future<Map<String, dynamic>?> restoreSession() async {
    final token = await _tokenStore.read();
    if (token == null) return null;
    try {
      final response = await _api.get('/v1/me');
      return Map<String, dynamic>.from(response as Map);
    } catch (_) {
      await _tokenStore.clear();
      return null;
    }
  }

  Future<void> logout() => _tokenStore.clear();
}
