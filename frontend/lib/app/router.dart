import 'package:go_router/go_router.dart';

import '../features/auth/login_screen.dart';
import '../features/auth/register_screen.dart';
import '../features/auth/splash_screen.dart';
import '../features/currency_shield/currency_shield_screen.dart';
import '../features/pockets/create_pocket_screen.dart';
import '../features/pockets/pockets_screen.dart';
import '../features/wallet/wallet_link_screen.dart';

/// Scope note: this router only wires the screens the FlowPilot handoff
/// doc calls for (auth, wallet linking, pockets, Currency Shield). The
/// original hackathon-flow screens (dashboard/activity/assistant/planning/
/// approval) were removed here because they import providers/models/
/// services/mock folders that don't exist in this repo and represent
/// features (wallet balances, transaction history, AI goal flow) the
/// handoff doc explicitly says not to build for this demo. Re-add them
/// once their supporting layer is actually implemented.
final GoRouter appRouter = GoRouter(
  initialLocation: '/splash',
  routes: [
    GoRoute(path: '/splash', builder: (context, state) => const SplashScreen()),
    GoRoute(path: '/login', builder: (context, state) => const LoginScreen()),
    GoRoute(path: '/register', builder: (context, state) => const RegisterScreen()),
    GoRoute(path: '/wallet-setup', builder: (context, state) => const WalletLinkScreen()),
    GoRoute(
      path: '/pockets',
      builder: (context, state) => const PocketsScreen(),
      routes: [
        GoRoute(
          path: 'create',
          builder: (context, state) => const CreatePocketScreen(),
        ),
      ],
    ),
    GoRoute(path: '/currency-shield', builder: (context, state) => const CurrencyShieldScreen()),
    // '/home' is used as the post-login landing route; point it at pockets
    // for now since there's no dashboard screen in scope yet.
    GoRoute(path: '/home', redirect: (context, state) => '/pockets'),
  ],
);
