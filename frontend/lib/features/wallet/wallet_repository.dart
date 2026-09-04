import '../../core/api_client.dart';
import '../../core/api_exception.dart';

class WalletRepository {
  WalletRepository({ApiClient? apiClient}) : _api = apiClient ?? ApiClient();

  final ApiClient _api;

  /// Links a public wallet address. A 409 means the user already has a
  /// wallet linked — treat that as success, not an error, per the handoff.
  Future<void> linkWallet({required String walletAddress, String currency = 'CNGN'}) async {
    try {
      await _api.post('/v1/wallets/link', data: {
        'wallet_address': walletAddress,
        'currency': currency,
      });
    } on ApiException catch (e) {
      if (e.isConflict) return; // already linked — not an error for the demo
      rethrow;
    }
  }
}
