import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../health_provider.dart';

/// Shows a persistent "Demo / simulated data" banner whenever /health
/// reports bmoni_mode: mock. Drop this at the top of any screen involved
/// in a money-moving flow.
class MockModeBanner extends ConsumerWidget {
  const MockModeBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final health = ref.watch(healthStatusProvider);

    return health.when(
      data: (status) {
        if (!status.isMockMode) return const SizedBox.shrink();
        return Container(
          width: double.infinity,
          color: Colors.amber.shade800,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: const Text(
            '⚠️ Demo mode — all data and transactions are simulated',
            style: TextStyle(color: Colors.black, fontWeight: FontWeight.w600, fontSize: 12),
            textAlign: TextAlign.center,
          ),
        );
      },
      loading: () => const SizedBox.shrink(),
      error: (_, __) => Container(
        width: double.infinity,
        color: Colors.red.shade800,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: const Text(
          'Could not reach the backend. Is it running?',
          style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 12),
          textAlign: TextAlign.center,
        ),
      ),
    );
  }
}
