import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/app_colors.dart';
import '../../app/theme/app_spacing.dart';
import '../../app/theme/app_typography.dart';
import '../../core/utils/formatters.dart';
import '../../core/widgets/transaction_row.dart';
import '../../providers/wallet_provider.dart';

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(walletProvider);
    final wallet = state.wallet;

    final balance = wallet?.balance ?? 0;

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        elevation: 0,
        title: const Text('FlowPilot × BMONI'),
        actions: [
          IconButton(
            onPressed: () => context.push('/profile'),
            icon: const Icon(Icons.person_outline),
          ),
        ],
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Good evening, Theresa',
                style: AppTypography.title,
              ),
              const SizedBox(height: 6),
              const Text(
                'Manage your money with confidence.',
                style: AppTypography.muted,
              ),

              const SizedBox(height: AppSpacing.lg),

              // Balance
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(20),
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
                      'Available Balance',
                      style: AppTypography.muted,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      formatCurrency(balance),
                      style: AppTypography.amount,
                    ),
                    const SizedBox(height: 4),
                    const Text(
                      'CNGN',
                      style: AppTypography.muted,
                    ),
                  ],
                ),
              ),

              const SizedBox(height: AppSpacing.lg),

              // Quick actions
              Row(
                children: [
                  Expanded(
                    child: _QuickAction(
                      icon: Icons.arrow_upward,
                      label: 'Send',
                      onTap: () {},
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: _QuickAction(
                      icon: Icons.arrow_downward,
                      label: 'Receive',
                      onTap: () {},
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: _QuickAction(
                      icon: Icons.account_balance,
                      label: 'Withdraw',
                      onTap: () => context.push('/assistant'),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: _QuickAction(
                      icon: Icons.add,
                      label: 'Add',
                      onTap: () {},
                    ),
                  ),
                ],
              ),

              const SizedBox(height: AppSpacing.lg),

              // FlowPilot
              GestureDetector(
                onTap: () => context.push('/assistant'),
                child: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    color: AppColors.elevated,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(
                      color: AppColors.accent,
                    ),
                  ),
                  child: const Row(
                    children: [
                      Icon(
                        Icons.auto_awesome,
                        color: AppColors.accent,
                        size: 30,
                      ),
                      SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'FlowPilot',
                              style: TextStyle(
                                color: AppColors.primaryText,
                                fontSize: 18,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                            SizedBox(height: 5),
                            Text(
                              'Tell me what you want to do with your money.',
                              style: AppTypography.muted,
                            ),
                          ],
                        ),
                      ),
                      Icon(
                        Icons.chevron_right,
                        color: AppColors.secondaryText,
                      ),
                    ],
                  ),
                ),
              ),

              const SizedBox(height: AppSpacing.xl),

              // Assets
              const Text(
                'Assets',
                style: AppTypography.section,
              ),
              const SizedBox(height: 10),

              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: AppColors.surface,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  children: [
                    const CircleAvatar(
                      backgroundColor: AppColors.elevated,
                      child: Text(
                        '₦',
                        style: TextStyle(
                          color: AppColors.accent,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    const Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'CNGN',
                            style: TextStyle(
                              color: AppColors.primaryText,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          SizedBox(height: 3),
                          Text(
                            '100%',
                            style: AppTypography.muted,
                          ),
                        ],
                      ),
                    ),
                    Text(
                      formatCurrency(balance),
                      style: const TextStyle(
                        color: AppColors.primaryText,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(height: AppSpacing.xl),

              // Recent activity
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text(
                    'Recent Activity',
                    style: AppTypography.section,
                  ),
                  TextButton(
                    onPressed: () => context.push('/activity'),
                    child: const Text('View All'),
                  ),
                ],
              ),

              const SizedBox(height: 4),

              if (state.loading && state.transactions.isEmpty)
                const Center(
                  child: Padding(
                    padding: EdgeInsets.all(24),
                    child: CircularProgressIndicator(),
                  ),
                )
              else if (state.transactions.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 24),
                  child: Center(
                    child: Text(
                      'No transactions yet.',
                      style: AppTypography.muted,
                    ),
                  ),
                )
              else
                ...state.transactions.take(4).map(
                      (tx) => TransactionRow(
                        tx: tx,
                        onTap: () => context.push(
                          '/transaction/${tx.id}',
                        ),
                      ),
                    ),
            ],
          ),
        ),
      ),
    );
  }
}

class _QuickAction extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  const _QuickAction({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 14),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: AppColors.border,
          ),
        ),
        child: Column(
          children: [
            Icon(
              icon,
              color: AppColors.primaryText,
              size: 20,
            ),
            const SizedBox(height: 6),
            Text(
              label,
              style: AppTypography.muted,
            ),
          ],
        ),
      ),
    );
  }
}