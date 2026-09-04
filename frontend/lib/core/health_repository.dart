import 'api_client.dart';

class HealthStatus {
  const HealthStatus({required this.isOk, required this.isMockMode});

  final bool isOk;
  final bool isMockMode;
}

class HealthRepository {
  HealthRepository({ApiClient? apiClient}) : _api = apiClient ?? ApiClient();

  final ApiClient _api;

  Future<HealthStatus> check() async {
    try {
      final response = await _api.get('/health');
      final map = Map<String, dynamic>.from(response as Map);
      return HealthStatus(
        isOk: map['status'] == 'ok',
        isMockMode: map['bmoni_mode'] == 'mock',
      );
    } catch (_) {
      return const HealthStatus(isOk: false, isMockMode: true);
    }
  }
}
