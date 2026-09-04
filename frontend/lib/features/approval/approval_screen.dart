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
import '../../providers/transaction_provider.dart';

class ApprovalScreen extends ConsumerStatefulWidget {
  const ApprovalScreen({super.key});

  @override
  ConsumerState<ApprovalScreen> createState() => _ApprovalState();
}

class _ApprovalState extends ConsumerState<ApprovalScreen> {
  bool checked = false;

  @override
  Widget build(BuildContext context) {
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
            Row(
              children: [
                IconButton(
                  onPressed: () {
                    context.pop();
                  },
                  icon: const Icon(Icons.arrow_back),
                ),
                const Text(
                  'Approve Transaction',
                  style: AppTypography.title,
                ),
              ],
            ),

            const SizedBox(height: 22),

            Container(
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: AppColors.border,
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'You’re about to withdraw',
                    style: AppTypography.muted,
                  ),

                  const SizedBox(height: 5),

                  Text(
                    formatCurrency(plan.amount),
                    style: AppTypography.amount,
                  ),

                  const SizedBox(height: 5),

                  const Text(
                    'to your linked GTBank account.',
                    style: AppTypography.muted,
                  ),

                  const SizedBox(height: 18),

                  const Divider(),

                  const DetailRow(
                    label: 'Amount',
                    value: '₦100,000.00',
                  ),

                  DetailRow(
                    label: 'Fee',
                    value: formatCurrency(plan.fee),
                  ),

                  DetailRow(
                    label: 'Remaining balance',
                    value: formatCurrency(plan.remainingBalance),
                    strong: true,
                  ),
                ],
              ),
            ),

            const SizedBox(height: 18),

            CheckboxListTile(
              value: checked,
              onChanged: (value) {
                setState(() {
                  checked = value ?? false;
                });
              },
              contentPadding: EdgeInsets.zero,
              controlAffinity: ListTileControlAffinity.leading,
              title: const Text(
                'I have reviewed and approve this transaction.',
                style: TextStyle(
                  fontSize: 13,
                ),
              ),
              activeColor: AppColors.accent,
              checkColor: Colors.black,
            ),

            const SizedBox(height: 20),

            PrimaryButton(
              label: 'Approve Transaction',
              onPressed: checked
                  ? () async {
                      await ref
                          .read(transactionProvider.notifier)
                          .createProposal(plan);

                      if (mounted) {
                        context.push('/signing');
                      }
                    }
                  : null,
            ),

            const SizedBox(height: 10),

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
}