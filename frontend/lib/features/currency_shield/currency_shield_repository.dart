import '../../core/api_client.dart';

class CurrencyShieldRecommendation {
  const CurrencyShieldRecommendation({
    required this.id,
    required this.status,
    required this.rationale,
    required this.riskDisclosure,
    required this.evidence,
  });

  factory CurrencyShieldRecommendation.fromJson(Map<String, dynamic> json) {
    return CurrencyShieldRecommendation(
      id: json['id'] as String,
      status: json['status'] as String,
      rationale: json['rationale'] as String,
      riskDisclosure: json['risk_disclosure'] as String,
      evidence: Map<String, dynamic>.from(json['evidence'] as Map? ?? {}),
    );
  }

  final String id;
  final String status;
  final String rationale;
  final String riskDisclosure;
  final Map<String, dynamic> evidence;
}

class CurrencyShieldRepository {
  CurrencyShieldRepository({ApiClient? apiClient}) : _api = apiClient ?? ApiClient();

  final ApiClient _api;

  Future<CurrencyShieldRecommendation> evaluate({
    required String pocketId,
    required int amountMinor,
    String targetCurrency = 'USD',
    int observedChangeBps = -500,
    int observationWindowDays = 30,
  }) async {
    final response = await _api.post('/v1/recommendations/currency-shield', data: {
      'pocket_id': pocketId,
      'target_currency': targetCurrency,
      'amount_minor': amountMinor,
      'observed_change_bps': observedChangeBps,
      'observation_window_days': observationWindowDays,
    });
    return CurrencyShieldRecommendation.fromJson(Map<String, dynamic>.from(response as Map));
  }

  /// [idempotencyKey] must be generated once per approval attempt and
  /// reused on retries — never regenerated — so a double-tap or timeout
  /// retry can't create two conversions.
  Future<Map<String, dynamic>> approve({
    required String recommendationId,
    required String idempotencyKey,
  }) async {
    final response = await _api.post(
      '/v1/recommendations/$recommendationId/approve',
      headers: {'Idempotency-Key': idempotencyKey},
    );
    return Map<String, dynamic>.from(response as Map);
  }
}
