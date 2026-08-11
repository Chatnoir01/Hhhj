# Architecture cible — Pilot

## Principes

Pilot sépare l'interface, le domaine métier et l'infrastructure. Les calculs fiscaux et la numérotation ne doivent pas dépendre du navigateur ni de la base de données.

## Couches

### 1. Frontend
Application responsive pour tableau de bord, clients, devis, factures et paramètres. Le frontend ne doit jamais être l'autorité finale sur les montants enregistrés.

### 2. API
API HTTP versionnée. Responsabilités : authentification, autorisation, validation, orchestration et sérialisation.

### 3. Domaine
Fonctions déterministes pour :
- calcul des montants ;
- validation des documents ;
- numérotation ;
- transitions de statut ;
- règles devis → facture.

### 4. Persistance
Cible : PostgreSQL avec transactions. Toute donnée métier appartient à un tenant/une entreprise. Les requêtes doivent systématiquement être filtrées par tenant_id côté serveur.

## Entités principales

- User
- Organization
- Membership
- Client
- Quote
- QuoteLine
- Invoice
- InvoiceLine
- Payment
- Reminder
- AuditEvent

## Règles structurelles

1. Les montants sont stockés en unités monétaires précises, idéalement en cents entiers côté persistance.
2. Une facture émise ne doit pas être silencieusement réécrite : les changements sensibles doivent laisser une trace d'audit.
3. Les numéros de facture sont attribués côté serveur dans une transaction afin d'éviter les collisions concurrentes.
4. Les documents PDF sont générés à partir d'un snapshot immuable des données du document.
5. Les secrets ne sont jamais envoyés au navigateur.
6. Toute action d'un utilisateur doit être autorisée contre son organisation courante.

## Phases

### Phase A — réalisée en partie
- UX dashboard
- clients locaux
- création locale de facture
- domaine calcul/validation
- serveur HTTP
- tests unitaires
- CI

### Phase B
- PostgreSQL
- migrations
- repository layer
- API CRUD clients/factures
- tests d'intégration

### Phase C
- authentification
- multi-tenant
- audit log
- génération PDF
- paramètres entreprise

### Phase D
- devis
- paiements
- relances
- exports comptables
- observabilité
- sauvegardes/restauration
