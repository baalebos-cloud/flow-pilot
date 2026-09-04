import 'package:bkey_uikit/bkey_uikit.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';

import '../../core/api_exception.dart';
import '../../core/money_formatter.dart';
import '../../core/widgets/mock_mode_banner.dart';
import '../pockets/pocket_model.dart';
import '../pockets/pockets_provider.dart';
import 'currency_shield_repository.dart';
import 'reason_copy.dart';

final currencyShieldRepositoryProvider =
    Provider<CurrencyShieldRepository>((ref) => CurrencyShieldRepository());

enum _Step { select, review, result }

class CurrencyShieldScreen extends ConsumerStatefulWidget {
  const CurrencyShieldScreen({super.key});

  @override
  ConsumerState<CurrencyShieldScreen> createState() => _CurrencyShieldScreenState();
}

class _CurrencyShieldScreenState extends ConsumerState<CurrencyShieldScreen> {
  _Step _step = _Step.select;
  Pocket? _selectedPocket;
  final _amountController = TextEditingController();

  bool _isBusy = false;
  CurrencyShieldRecommendation? _recommendation;
  String? _idempotencyKey; // generated once per approval attempt, reused on retry
  Map<String, dynamic>? _result;

  @override
  void dispose() {
    _amountController.dispose();
    super.dispose();
  }

  Future<void> _requestEvaluation() async {
    final pocket = _selectedPocket;
    final majorValue = double.tryParse(_amountController.text.trim());
    if (pocket == null || majorValue == null || majorValue <= 0) {
      BMoniToastOverlay.showError(context: context, message: 'Pick a pocket and enter an amount');
      return;
    }

    setState(() => _isBusy = true);
    try {
      final recommendation = await ref.read(currencyShieldRepositoryProvider).evaluate(
            pocketId: pocket.id,
            amountMinor: (majorValue * 100).round(),
          );
      setState(() {
        _recommendation = recommendation;
        _step = _Step.review;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      final message = e.isValidationRejection && e.reasons != null
          ? friendlyReasons(e.reasons!)
          : e.message;
      BMoniToastOverlay.showError(context: context, message: message);
    } finally {
      if (mounted) setState(() => _isBusy = false);
    }
  }

  Future<void> _approve() async {
    final recommendation = _recommendation;
    if (recommendation == null) return;

    // Generate the idempotency key once, the first time approval begins.
    // If this call times out or the user retries, we reuse the same key —
    // never a fresh one — so a double-tap can't create two conversions.
    _idempotencyKey ??= const Uuid().v4();

    setState(() => _isBusy = true);
    try {
      final result = await ref.read(currencyShieldRepositoryProvider).approve(
            recommendationId: recommendation.id,
            idempotencyKey: _idempotencyKey!,
          );
      setState(() {
        _result = result;
        _step = _Step.result;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      BMoniToastOverlay.showError(context: context, message: e.message);
      // Keep the same idempotency key for a retry — do not clear it here.
    } finally {
      if (mounted) setState(() => _isBusy = false);
    }
  }

  void _startOver() {
    setState(() {
      _step = _Step.select;
      _selectedPocket = null;
      _amountController.clear();
      _recommendation = null;
      _idempotencyKey = null;
      _result = null;
    });
    ref.read(pocketsProvider.notifier).refresh();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: const CustomAppBar(title: 'Currency Shield', showBackButton: false),
      body: SafeArea(
        child: Column(
          children: [
            const MockModeBanner(),
            Expanded(
              child: switch (_step) {
                _Step.select => _SelectStep(
                    amountController: _amountController,
                    selectedPocket: _selectedPocket,
                    onPocketSelected: (pocket) => setState(() => _selectedPocket = pocket),
                    isBusy: _isBusy,
                    onContinue: _requestEvaluation,
                  ),
                _Step.review => _ReviewStep(
                    recommendation: _recommendation!,
                    pocket: _selectedPocket!,
                    amountMinor: ((double.tryParse(_amountController.text.trim()) ?? 0) * 100).round(),
                    isBusy: _isBusy,
                    onApprove: _approve,
                    onCancel: _startOver,
                  ),
                _Step.result => _ResultStep(result: _result!, onDone: _startOver),
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _SelectStep extends ConsumerWidget {
  const _SelectStep({
    required this.amountController,
    required this.selectedPocket,
    required this.onPocketSelected,
    required this.isBusy,
    required this.onContinue,
  });

  final TextEditingController amountController;
  final Pocket? selectedPocket;
  final ValueChanged<Pocket> onPocketSelected;
  final bool isBusy;
  final VoidCallback onContinue;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final pocketsAsync = ref.watch(pocketsProvider);

    return pocketsAsync.when(
      data: (pockets) {
        // Only non-protected CNGN pockets are eligible per the handoff.
        final eligible = pockets.where((p) => !p.protected && p.currency == 'CNGN').toList();

        return SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              HeadingText('Evaluate a conversion', level: 4, weight: HeadingWeight.semibold),
              const SizedBox(height: 16),
              if (eligible.isEmpty)
                InfoCard(
                  title: 'No eligible pockets',
                  message: 'Create a non-protected CNGN pocket first.',
                  icon: Icons.info_outline,
                )
              else ...[
                LabelText('Pocket', size: LabelSize.medium, weight: LabelWeight.medium),
                const SizedBox(height: 8),
                ...eligible.map(
                  (pocket) => RadioListTile<Pocket>(
                    contentPadding: EdgeInsets.zero,
                    title: Text(pocket.name),
                    subtitle: Text(
                      'Available: ${MoneyFormatter.format(pocket.availableMinor, currency: pocket.currency)}',
                    ),
                    value: pocket,
                    groupValue: selectedPocket,
                    onChanged: (value) => value != null ? onPocketSelected(value) : null,
                  ),
                ),
                const SizedBox(height: 16),
                BMoniTextFormField.filled(
                  label: 'Amount to convert (CNGN)',
                  hintText: '40000.00',
                  controller: amountController,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                ),
                const SizedBox(height: 24),
                BMoniButton.primary(
                  onPressed: (isBusy || selectedPocket == null) ? null : onContinue,
                  text: 'Get recommendation',
                  isLoading: isBusy,
                ),
              ],
            ],
          ),
        );
      },
      loading: () => const Center(child: ProgressLoaderWidget()),
      error: (error, _) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 40),
              const SizedBox(height: 12),
              Text(error.toString(), textAlign: TextAlign.center),
              const SizedBox(height: 16),
              BMoniButton.outline(
                onPressed: () => ref.refresh(pocketsProvider),
                text: 'Retry',
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ReviewStep extends StatelessWidget {
  const _ReviewStep({
    required this.recommendation,
    required this.pocket,
    required this.amountMinor,
    required this.isBusy,
    required this.onApprove,
    required this.onCancel,
  });

  final CurrencyShieldRecommendation recommendation;
  final Pocket pocket;
  final int amountMinor;
  final bool isBusy;
  final VoidCallback onApprove;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          HeadingText('Review recommendation', level: 4, weight: HeadingWeight.semibold),
          const SizedBox(height: 16),
          ActivitySectionCard(
            header: const SectionHeader(title: 'Rationale'),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: BodyText(recommendation.rationale, size: BodySize.medium, weight: BodyWeight.regular),
            ),
          ),
          const SizedBox(height: 12),
          ActivitySectionCard(
            header: const SectionHeader(title: 'Risk disclosure'),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: BodyText(recommendation.riskDisclosure, size: BodySize.medium, weight: BodyWeight.regular),
            ),
          ),
          const SizedBox(height: 12),
          ActivitySectionCard(
            header: const SectionHeader(title: 'Details'),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('From: ${MoneyFormatter.format(amountMinor, currency: pocket.currency)} (${pocket.currency})'),
                  const SizedBox(height: 4),
                  const Text('To: USD'),
                ],
              ),
            ),
          ),
          const SizedBox(height: 32),
          BMoniButton.primary(
            onPressed: isBusy ? null : onApprove,
            text: 'Approve',
            isLoading: isBusy,
          ),
          const SizedBox(height: 12),
          BMoniButton.outline(
            onPressed: isBusy ? null : onCancel,
            text: 'Cancel',
          ),
        ],
      ),
    );
  }
}

class _ResultStep extends StatelessWidget {
  const _ResultStep({required this.result, required this.onDone});

  final Map<String, dynamic> result;
  final VoidCallback onDone;

  @override
  Widget build(BuildContext context) {
    final status = result['status']?.toString() ?? 'UNKNOWN';

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          HeadingText('Conversion result', level: 4, weight: HeadingWeight.semibold),
          const SizedBox(height: 8),
          StatusText(
            status,
            status: status.toUpperCase().contains('FAIL') ? StatusType.error : StatusType.success,
          ),
          const SizedBox(height: 16),
          InfoCard(
            title: 'Simulated',
            message: 'This demo runs in mock mode — no real money moved.',
            icon: Icons.info_outline,
          ),
          const SizedBox(height: 16),
          ActivitySectionCard(
            header: const SectionHeader(title: 'Quote'),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: result.entries
                    .map((entry) => Padding(
                          padding: const EdgeInsets.symmetric(vertical: 4),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(entry.key),
                              Flexible(child: Text('${entry.value}', textAlign: TextAlign.right)),
                            ],
                          ),
                        ))
                    .toList(),
              ),
            ),
          ),
          const SizedBox(height: 24),
          BMoniButton.primary(onPressed: onDone, text: 'Done'),
        ],
      ),
    );
  }
}
