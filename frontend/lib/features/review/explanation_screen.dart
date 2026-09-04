import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/app_colors.dart';
import '../../app/theme/app_typography.dart';
import '../../core/utils/formatters.dart';
import '../../core/widgets/detail_row.dart';
import '../../core/widgets/primary_button.dart';
import '../../providers/goal_provider.dart';

class ExplanationScreen extends ConsumerWidget {
  const ExplanationScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(goalProvider);
    final plan = state.plan;

    if (plan == null) {
      return const Scaffold(
        body: Center(
          child: CircularProgressIndicator(
            color: AppColors.accent,
          ),
        ),
      );
    }

    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 18, 20, 30),
          children: [
            // Header
            Row(
              children: [
                IconButton(
                  onPressed: () {
                    context.pop();
                  },
                  icon: const Icon(Icons.arrow_back),
                ),
                const Text(
                  'Why this action?',
                  style: AppTypography.title,
                ),
              ],
            ),

            const SizedBox(height: 20),

            // Your request
            _box(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Your request',
                    style: AppTypography.section,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    state.input,
                    style: AppTypography.muted,
                  ),
                ],
              ),
            ),

            const SizedBox(height: 14),

            // What FlowPilot understood
            _box(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'What FlowPilot understood',
                    style: AppTypography.section,
                  ),
                  const SizedBox(height: 10),

                  const DetailRow(
                    label: 'Action',
                    value: 'Bank withdrawal',
                  ),

                  DetailRow(
                    label: 'Amount',
                    value: formatCurrency(plan.amount),
                  ),

                  const DetailRow(
                    label: 'Destination',
                    value: 'GTBank ••••4821',
                  ),
                ],
              ),
            ),

            const SizedBox(height: 14),

            // Why it is allowed
            _box(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Why it’s allowed',
                    style: AppTypography.section,
                  ),

                  const SizedBox(height: 10),

                  _checkItem('Sufficient balance'),
                  _checkItem('Valid destination'),
                  _checkItem('Within transaction limits'),
                  _checkItem('Explicit approval required'),
                ],
              ),
            ),

            const SizedBox(height: 14),

            // Security information
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: AppColors.accent.withOpacity(0.07),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                  color: AppColors.accent.withOpacity(0.2),
                ),
              ),
              child: const Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    Icons.lock_outline,
                    color: AppColors.accent,
                    size: 20,
                  ),
                  SizedBox(width: 11),
                  Expanded(
                    child: Text(
                      'FlowPilot does not execute transactions automatically. '
                      'You remain in control and must approve the action '
                      'before the transaction can proceed.',
                      style: TextStyle(
                        fontSize: 13,
                        height: 1.45,
                      ),
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 24),

            // Continue
            PrimaryButton(
              label: 'Continue to Review',
              onPressed: () {
                context.push('/review');
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _checkItem(String text) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(
        children: [
          const Icon(
            Icons.check_circle,
            size: 18,
            color: AppColors.success,
          ),
          const SizedBox(width: 9),
          Expanded(
            child: Text(
              text,
              style: const TextStyle(
                fontSize: 13,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _box({
    required Widget child,
  }) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: AppColors.border,
        ),
      ),
      child: child,
    );
  }
}