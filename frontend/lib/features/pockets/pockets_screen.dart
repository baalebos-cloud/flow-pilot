import 'package:bkey_uikit/bkey_uikit.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/money_formatter.dart';
import '../../core/widgets/mock_mode_banner.dart';
import 'pocket_model.dart';
import 'pockets_provider.dart';

class PocketsScreen extends ConsumerWidget {
  const PocketsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final pocketsAsync = ref.watch(pocketsProvider);

    return Scaffold(
      appBar: CustomAppBar(
        title: 'Pockets',
        showBackButton: false,
        actions: [
          TextButton(
            onPressed: () => context.push('/currency-shield'),
            child: const Text('Currency Shield'),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => context.push('/pockets/create'),
        child: const Icon(Icons.add),
      ),
      body: SafeArea(
        child: Column(
          children: [
            const MockModeBanner(),
            Expanded(
              child: RefreshIndicator(
                onRefresh: () => ref.read(pocketsProvider.notifier).refresh(),
                child: pocketsAsync.when(
                  data: (pockets) {
                    if (pockets.isEmpty) {
                      return ListView(
                        children: [
                          const SizedBox(height: 80),
                          EmptyState(
                            svgAsset: 'assets/svgs/empty_box.svg',
                            message: 'No pockets yet',
                            subtitle: 'Create a pocket to start allocating funds.',
                            buttonText: 'Create pocket',
                            onButtonPressed: () => context.push('/pockets/create'),
                          ),
                        ],
                      );
                    }
                    return ListView.separated(
                      padding: const EdgeInsets.all(16),
                      itemCount: pockets.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 12),
                      itemBuilder: (context, index) => _PocketCard(pocket: pockets[index]),
                    );
                  },
                  loading: () => const Center(child: ProgressLoaderWidget()),
                  error: (error, _) => ListView(
                    children: [
                      const SizedBox(height: 80),
                      _ErrorRetry(
                        message: error.toString(),
                        onRetry: () => ref.read(pocketsProvider.notifier).refresh(),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PocketCard extends StatelessWidget {
  const _PocketCard({required this.pocket});

  final Pocket pocket;

  @override
  Widget build(BuildContext context) {
    return ActivitySectionCard(
      header: SectionHeader(
        title: pocket.name,
        trailing: pocket.protected
            ? const Chip(label: Text('Protected'), avatar: Icon(Icons.lock, size: 14))
            : null,
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            BodyText(pocket.purpose, size: BodySize.small, weight: BodyWeight.regular),
            const SizedBox(height: 12),
            _AmountRow(label: 'Allocated', minor: pocket.allocatedMinor, currency: pocket.currency),
            _AmountRow(label: 'Spent', minor: pocket.spentMinor, currency: pocket.currency),
            _AmountRow(label: 'Available', minor: pocket.availableMinor, currency: pocket.currency, emphasize: true),
          ],
        ),
      ),
    );
  }
}

/// Simple retry state. Swap for bkey_uikit's FailureWidget once its exact
/// constructor is confirmed with the design team — it wasn't fully
/// documented alongside EmptyState/ProgressLoaderWidget.
class _ErrorRetry extends StatelessWidget {
  const _ErrorRetry({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        children: [
          const Icon(Icons.error_outline, size: 40),
          const SizedBox(height: 12),
          Text(message, textAlign: TextAlign.center),
          const SizedBox(height: 16),
          BMoniButton.outline(onPressed: onRetry, text: 'Retry'),
        ],
      ),
    );
  }
}

class _AmountRow extends StatelessWidget {
  const _AmountRow({
    required this.label,
    required this.minor,
    required this.currency,
    this.emphasize = false,
  });

  final String label;
  final int minor;
  final String currency;
  final bool emphasize;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          LabelText(label, size: LabelSize.small, weight: LabelWeight.medium),
          Text(
            MoneyFormatter.format(minor, currency: currency),
            style: TextStyle(fontWeight: emphasize ? FontWeight.bold : FontWeight.normal),
          ),
        ],
      ),
    );
  }
}
