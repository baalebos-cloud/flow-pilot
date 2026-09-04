import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'health_repository.dart';

final healthRepositoryProvider = Provider<HealthRepository>((ref) => HealthRepository());

final healthStatusProvider = FutureProvider<HealthStatus>((ref) {
  return ref.watch(healthRepositoryProvider).check();
});
