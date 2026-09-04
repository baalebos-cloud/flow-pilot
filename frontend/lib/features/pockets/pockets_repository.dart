import '../../core/api_client.dart';
import 'pocket_model.dart';

class PocketsRepository {
  PocketsRepository({ApiClient? apiClient}) : _api = apiClient ?? ApiClient();

  final ApiClient _api;

  Future<List<Pocket>> list() async {
    final response = await _api.get('/v1/pockets');
    final items = List<Map<String, dynamic>>.from(response as List);
    return items.map(Pocket.fromJson).toList();
  }

  Future<Pocket> create({
    required String name,
    required String purpose,
    required int allocatedMinor,
    String currency = 'CNGN',
    bool protected = false,
  }) async {
    final response = await _api.post('/v1/pockets', data: {
      'name': name,
      'purpose': purpose,
      'allocated_minor': allocatedMinor,
      'currency': currency,
      'protected': protected,
    });
    return Pocket.fromJson(Map<String, dynamic>.from(response as Map));
  }
}
