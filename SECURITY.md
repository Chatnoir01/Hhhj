# Security

Pilot est en phase de développement. Ne pas utiliser ce dépôt comme système de facturation de production tant que l'authentification, la persistance sécurisée, les sauvegardes, les journaux d'audit et les contrôles de conformité ne sont pas terminés.

## Baseline appliquée
- aucune clé ou secret dans le dépôt ;
- limite de taille sur les payloads JSON ;
- validation des entrées du domaine facture ;
- en-têtes de sécurité HTTP sur les ressources statiques ;
- Content-Security-Policy restrictive ;
- erreurs API structurées sans exposition de stack trace ;
- CI avec permissions minimales en lecture.

## Avant production
- authentification forte et sessions sécurisées ;
- isolation stricte multi-tenant ;
- base de données transactionnelle ;
- chiffrement des secrets et sauvegardes ;
- rate limiting ;
- protection CSRF selon le mode d'authentification ;
- journal d'audit immuable des actions sensibles ;
- politique de rétention et suppression ;
- tests d'autorisation horizontale/verticale ;
- revue des obligations légales et fiscales applicables.

## Signaler une vulnérabilité
Ne pas publier de données personnelles, credentials ou secrets dans une issue publique. Utiliser un canal privé avant toute divulgation publique.
