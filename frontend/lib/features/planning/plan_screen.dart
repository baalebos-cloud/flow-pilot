import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/app_colors.dart';
import '../../app/theme/app_typography.dart';
import '../../core/utils/formatters.dart';
import '../../core/widgets/detail_row.dart';
import '../../core/widgets/primary_button.dart';
import '../../core/widgets/secondary_button.dart';
import '../../core/widgets/status_badge.dart';
import '../../providers/goal_provider.dart';

class PlanScreen extends ConsumerWidget {
  const PlanScreen({super.key});

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
                  'Your Plan',
                  style: AppTypography.title,
                ),
              ],
            ),

            const SizedBox(height: 20),

            // Amount
            Center(
              child: Column(
                children: [
                  Text(
                    formatCurrency(plan.amount),
                    style: AppTypography.display,
                  ),
                  const SizedBox(height: 4),
                  const Text(
                    'Bank Withdrawal',
                    style: AppTypography.muted,
                  ),
                ],
              ),
            ),

            const SizedBox(height: 22),

            // Transaction details
            _card(
              child: Column(
                children: [
                  const DetailRow(
                    label: 'From',
                    value: 'FlowPilot Wallet',
                  ),
                  const DetailRow(
                    label: 'To',
                    value: 'GTBank ••••4821',
                  ),
                  DetailRow(
                    label: 'Amount',
                    value: formatCurrency(plan.amount),
                    strong: true,
                  ),
                  DetailRow(
                    label: 'Fee',
                    value: formatCurrency(plan.fee),
                  ),
                  DetailRow(
                    label: 'Remaining Balance',
                    value: formatCurrency(plan.remainingBalance),
                    strong: true,
                  ),
                ],
              ),
            ),

            const SizedBox(height: 18),

            // Policy Check
            _card(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Policy Check',
                    style: AppTypography.section,
                  ),

                  const SizedBox(height: 10),

                  _policyItem('Balance sufficient'),
                  _policyItem('Amount within allowed limits'),
                  _policyItem('Destination available'),
                  _policyItem('User approval required'),

                  const SizedBox(height: 10),

                  const Row(
                    children: [
                      Text(
                        'Risk Status',
                        style: AppTypography.muted,
                      ),
                      Spacer(),
                      StatusBadge(
                        status: 'Approved',
                      ),
                    ],
                  ),
                ],
              ),
            ),

            const SizedBox(height: 18),

            // Explanation
            _card(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Why this action?',
                    style: AppTypography.section,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    plan.reason,
                    style: AppTypography.muted,
                  ),
                ],
              ),
            ),

            const SizedBox(height: 24),

            // Review button
            PrimaryButton(
              label: 'Review Action',
              onPressed: () {
                context.push('/explanation');
              },
            ),

            const SizedBox(height: 10),

            // Edit button
            SecondaryButton(
              label: 'Edit Goal',
              onPressed: () {
                context.pop();
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _policyItem(String text) {
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

  Widget _card({
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