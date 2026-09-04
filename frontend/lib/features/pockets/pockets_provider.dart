import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'pocket_model.dart';
import 'pockets_repository.dart';

final pocketsRepositoryProvider = Provider<PocketsRepository>((ref) => PocketsRepository());

class PocketsNotifier extends AsyncNotifier<List<Pocket>> {
  @override
  Future<List<Pocket>> build() => ref.read(pocketsRepositoryProvider).list();

  Future<void> refresh() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() => ref.read(pocketsRepositoryProvider).list());
  }

  Future<void> createPocket({
    required String name,
    required String purpose,
    required int allocatedMinor,
    String currency = 'CNGN',
    bool protected = false,
  }) async {
    await ref.read(pocketsRepositoryProvider).create(
          name: name,
          purpose: purpose,
          allocatedMinor: allocatedMinor,
          currency: currency,
          protected: protected,
        );
    await refresh();
  }
}

final pocketsProvider = AsyncNotifierProvider<PocketsNotifier, List<Pocket>>(PocketsNotifier.new);
