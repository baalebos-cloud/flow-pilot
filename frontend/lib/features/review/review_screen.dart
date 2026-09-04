import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/app_colors.dart';
import '../../app/theme/app_typography.dart';
import '../../core/utils/formatters.dart';
import '../../core/widgets/detail_row.dart';
import '../../core/widgets/primary_button.dart';
import '../../core/widgets/secondary_button.dart';
import '../../providers/goal_provider.dart';

class ReviewScreen extends ConsumerWidget {
  const ReviewScreen({super.key});

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
                  'Review Withdrawal',
                  style: AppTypography.title,
                ),
              ],
            ),

            const SizedBox(height: 20),

            // Amount
            Center(
              child: Text(
                formatCurrency(plan.amount),
                style: AppTypography.display,
              ),
            ),

            const SizedBox(height: 4),

            const Center(
              child: Text(
                'CNGN • Bank Withdrawal',
                style: AppTypography.muted,
              ),
            ),

            const SizedBox(height: 24),

            // Transaction details
            _box(
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
                  const DetailRow(
                    label: 'Network / Currency',
                    value: 'CNGN',
                  ),
                  DetailRow(
                    label: 'Fee',
                    value: formatCurrency(plan.fee),
                  ),
                  DetailRow(
                    label: 'You will receive',
                    value: formatCurrency(
                      plan.amount - plan.fee,
                    ),
                    strong: true,
                  ),
                  DetailRow(
                    label: 'Wallet balance after',
                    value: formatCurrency(
                      plan.remainingBalance,
                    ),
                    strong: true,
                  ),
                ],
              ),
            ),

            const SizedBox(height: 16),

            // Security check
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                  color: AppColors.border,
                ),
              ),
              child: const Row(
                children: [
                  Icon(
                    Icons.verified_user_outlined,
                    color: AppColors.accent,
                  ),
                  SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Security Check',
                          style: TextStyle(
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        SizedBox(height: 4),
                        Text(
                          'Your transaction will require your approval before signing.',
                          style: AppTypography.muted,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 24),

            // Approve
            PrimaryButton(
              label: 'Approve & Continue',
              onPressed: () {
                context.push('/approval');
              },
            ),

            const SizedBox(height: 10),

            // Cancel
            SecondaryButton(
              label: 'Cancel',
              onPressed: () {
                context.go('/home');
              },
            ),
          ],
        ),
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