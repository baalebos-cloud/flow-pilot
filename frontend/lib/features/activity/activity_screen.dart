import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/app_colors.dart';
import '../../app/theme/app_typography.dart';
import '../../core/widgets/transaction_row.dart';
import '../../providers/wallet_provider.dart';

class ActivityScreen extends ConsumerStatefulWidget {
  const ActivityScreen({super.key});

  @override
  ConsumerState<ActivityScreen> createState() => _ActivityState();
}

class _ActivityState extends ConsumerState<ActivityScreen> {
  int filter = 0;

  final List<String> filters = [
    'All',
    'Withdrawals',
    'Received',
    'Pending',
  ];

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(walletProvider);
    final allTransactions = state.transactions;

    final filteredTransactions = filter == 0
        ? allTransactions
        : allTransactions.where((transaction) {
            if (filter == 1) {
              return transaction.type.contains('Withdrawal');
            }

            if (filter == 2) {
              return transaction.type == 'Received';
            }

            return transaction.status == 'Pending';
          }).toList();

    return SafeArea(
      child: ListView(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 30),
        children: [
          const Text(
            'Activity',
            style: AppTypography.title,
          ),

          const SizedBox(height: 18),

          // Filter buttons
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                for (int i = 0; i < filters.length; i++)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                      label: Text(filters[i]),
                      selected: filter == i,
                      onSelected: (_) {
                        setState(() {
                          filter = i;
                        });
                      },
                      selectedColor: AppColors.accent.withOpacity(0.15),
                      labelStyle: TextStyle(
                        color: filter == i
                            ? AppColors.accent
                            : AppColors.secondaryText,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
              ],
            ),
          ),

          const SizedBox(height: 18),

          // Empty state
          if (filteredTransactions.isEmpty)
            Container(
              padding: const EdgeInsets.all(28),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                  color: AppColors.border,
                ),
              ),
              child: const Column(
                children: [
                  Icon(
                    Icons.receipt_long_outlined,
                    size: 34,
                    color: AppColors.secondaryText,
                  ),
                  SizedBox(height: 10),
                  Text(
                    'No transactions found',
                    style: AppTypography.section,
                  ),
                ],
              ),
            ),

          // Transactions
          if (filteredTransactions.isNotEmpty)
            for (final transaction in filteredTransactions)
              TransactionRow(
                tx: transaction,
                onTap: () {
                  context.push(
                    '/transaction/${transaction.id}',
                  );
                },
              ),
        ],
      ),
    );
  }
}