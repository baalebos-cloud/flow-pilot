import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../features/dashboard/dashboard_screen.dart';
import '../features/activity/activity_screen.dart';
import '../features/assistant/assistant_screen.dart';
import '../features/planning/plan_screen.dart';
import '../features/review/explanation_screen.dart';
import '../features/review/review_screen.dart';
import '../features/approval/approval_screen.dart';
import '../features/transaction/signing_screen.dart';
import '../features/transaction/processing_screen.dart';
import '../features/transaction/success_screen.dart';
import '../features/transaction/transaction_detail_screen.dart';
import '../features/wallet/wallet_screen.dart';
import '../features/profile/profile_screen.dart';

final GoRouter appRouter = GoRouter(
  initialLocation: '/home',
  routes: [
    GoRoute(
      path: '/home',
      builder: (context, state) => const DashboardScreen(),
    ),

    GoRoute(
      path: '/activity',
      builder: (context, state) => const ActivityScreen(),
    ),

    GoRoute(
      path: '/assistant',
      builder: (context, state) => const AssistantScreen(),
    ),

    GoRoute(
      path: '/planning',
      builder: (context, state) => const PlanScreen(),
    ),

    GoRoute(
      path: '/explanation',
      builder: (context, state) => const ExplanationScreen(),
    ),

    GoRoute(
      path: '/review',
      builder: (context, state) => const ReviewScreen(),
    ),

    GoRoute(
      path: '/approval',
      builder: (context, state) => const ApprovalScreen(),
    ),

    GoRoute(
      path: '/signing',
      builder: (context, state) => const SigningScreen(),
    ),

    GoRoute(
      path: '/processing',
      builder: (context, state) => const ProcessingScreen(),
    ),

    GoRoute(
      path: '/success',
      builder: (context, state) => const SuccessScreen(),
    ),

    GoRoute(
      path: '/transaction/:id',
      builder: (context, state) {
        final id = state.pathParameters['id'] ?? '';

        return TransactionDetailScreen(
          id: id,
        );
      },
    ),

    GoRoute(
      path: '/wallet',
      builder: (context, state) => const WalletScreen(),
    ),

    GoRoute(
      path: '/profile',
      builder: (context, state) => const ProfileScreen(),
    ),
  ],
);