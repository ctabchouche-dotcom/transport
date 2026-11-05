# Transport

Module Odoo 19 pour une compagnie de cars : lignes, départs, billets QR, embarquement, GPS fixé dans le bus, liste d'attente, contrats entreprise. Version `19.0.31.0.0`. Licence LGPL-3. Auteur : Chakib.

Le même texte est écrit quatre fois, une langue par section. Chaque section se suffit.

- [Français](#français)
- [English](#english)
- [Deutsch](#deutsch)
- [العربية](#العربية)

---

# Français

## Ce que le module fait

Une seule exploitation, deux ventes.

- **Billet individuel** : le passager réserve sur la page publique, paie sur la page de la compagnie, reçoit un reçu PDF et un billet avec QR.
- **Abonné entreprise** : le guichet confirme la place sur un contrat. L'abonné ne paie pas au guichet. Le relevé mensuel liste les trajets. Ce relevé n'est pas une facture comptable.

Le siège se compte par tronçon. Un passager Alger → Blida occupe les tronçons jusqu'à Blida. Après Blida, le même numéro de siège peut être revendu.

Les montants (encaissé, remboursé, carburant, péage, chauffeur, marge) restent dans le départ. Le module ne crée pas d'écriture `account.move`. Il ne dépend pas de Comptabilité, Ventes, Site web, ni Paiement.

## Ce qu'il faut installer, exactement

| Élément | Exigence |
| --- | --- |
| Odoo | 19.0. Le module utilise `models.Constraint`, les vues `<list>` et `<chatter/>`. |
| Python | 3.10 ou plus. Cet environnement utilise 3.13. |
| PostgreSQL | Une base dédiée. L'utilisateur de la base doit pouvoir créer des tables. |
| Modules Odoo | `base`, `mail`, `fleet`, `hr`. Odoo les installe avec Transport. |
| Paquet Python `qrcode` | Obligatoire. Le QR du billet est un PNG. Sans ce paquet, l'émission du billet plante. |
| Paquet Python `Pillow` | Obligatoire. `qrcode` enregistre le PNG avec Pillow. ReportLab n'est pas utilisé pour le QR. |
| wkhtmltopdf | Obligatoire pour le vrai PDF (billet, reçu, manifeste, relevé). Odoo 19 attend la version 0.12.6 avec Qt patché. Sous Windows, le binaire connu est `C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe`. |
| Boîtier GPS et lecteur de porte | Obligatoires pour la position et le passage automatiques. Voir les sections GPS et Scan. |
| Internet sur l'écran du bureau | Obligatoire pour la carte Leaflet. Le bus n'a besoin que d'un accès HTTP vers le serveur. |
| Serveur d'e-mail sortant | Facultatif pour vendre. Obligatoire pour que les messages partent vraiment. |
| Passerelle CIB, BaridiMob ou SATIM | Absente. Ne pas la chercher dans le module. |

Installation des paquets Python, dans le virtualenv d'Odoo :

```bash
pip install "qrcode" "Pillow"
```

Le dossier du module doit s'appeler `transport` et se trouver dans un répertoire listé par `addons_path`. Exemple de `odoo.conf` :

```ini
[options]
addons_path = /chemin/vers/odoo/addons,/chemin/vers/custom_addons
db_host = localhost
db_port = 5432
db_user = odoo
db_password = REMPLACER
http_port = 8069
```

Ne mettez pas le mot de passe de la base dans un fichier public.

Installation :

```bash
python odoo-bin -c odoo.conf -d NOM_DE_LA_BASE -i transport --stop-after-init
```

Mise à jour après un changement de code :

```bash
python odoo-bin -c odoo.conf -d NOM_DE_LA_BASE -u transport --stop-after-init
```

Puis redémarrer Odoo et ouvrir la base. Le menu **Transport** apparaît pour un utilisateur qui a le privilège Transport.

Tests du module, sur une base jetable, jamais sur la base des passagers :

```bash
python odoo-bin -c odoo.conf -d transport_ci -u transport --test-enable --test-tags /transport --stop-after-init --http-port=8071 --log-level=test
```

Le résultat attendu se termine par `0 failed, 0 error(s)`.

## Utilisateurs

Réglages → Utilisateurs → privilège **Transport**.

- **Dispatch** : départs, bus, chauffeur, réservations, scan, encaissement, GPS, statistiques, relevé.
- **Responsable** : tout le Dispatch, plus les lignes, les arrêts, les horaires, les contrats et les points de contrôle.

L'administrateur Odoo reçoit **Responsable** à l'installation. Un utilisateur interne sans ce privilège ne voit pas le menu. Le passager, lui, n'a pas de compte : les pages publiques sont en `auth='public'`.

## Réseau chargé à l'installation

| Code | Ligne | Type | Plan de sièges |
| --- | --- | --- | --- |
| ALG-MED | Alger – Médéa | Hybride | Car 2+2, banquette de 5 |
| ALG-ORN | Alger – Oran | Hybride | Porte avant, 2+2, banquette de 5 |
| ALG-CON | Alger – Constantine | Interurbain | Siège accompagnateur, puis 2+2 |
| ALG-TIZ | Navette Alger – Tizi Ouzou | Entreprise | Minibus 2+1, banquette de 4. Invisible sur la page publique. |
| ORN-TLM | Oran – Tlemcen | Hybride | Car 2+2, banquette de 5 |
| CON-ANN | Constantine – Annaba | Interurbain | Car 2+2 jusqu'au fond |
| ALG-BEJ | Alger – Béjaïa | Hybride | Midibus 2+2, coffre arrière |

La décoration d'exploitation (contrats, départs d'exemple, billets d'exemple) ne s'exécute qu'une fois, grâce au paramètre `transport.algeria_ops_ready`. Relancer `-u transport` ne la rejoue pas. Les séquences et les e-mails sont en `noupdate="1"` : les modifier dans le XML ne met pas à jour une base déjà installée.

Vous pouvez ignorer ce réseau et créer le vôtre. Pour qu'une ligne se vende, il faut les éléments de la section suivante. Un tarif manquant bloque la vente avec le message « Ce trajet n'a pas de prix. »

## Réglage minimum d'une ligne qui se vend

1. **Arrêts**, avec un code unique.
2. **Ligne** : code, type, capacité, alignement des sièges, vitesse moyenne (70 km/h par défaut).
3. **Arrêts de la ligne**, dans l'ordre. Le champ distance est le nombre de kilomètres **depuis l'arrêt précédent**. C'est cette distance, divisée par la vitesse, qui donne l'heure de passage. Un retard décale toutes les heures du même nombre de minutes.
4. **Tarif par couple montée / descente**, dans l'onglet Tarifs. Le champ « Prix bout en bout » est indicatif. La page publique ne l'utilise pas.
5. **Horaire** : jours et heure.
6. **Exploitation → Générer les départs**, sur une plage de dates.
7. **Flotte → Véhicules** : un bus avec un nombre de sièges et un alignement. L'alignement du bus remplace celui de la ligne dès qu'il contient exactement la capacité du départ. Sinon le départ garde l'alignement de la ligne, puis `coach_2_2`.
8. **Employés** : le chauffeur est un `hr.employee` de la même société. **Configuration → Itinéraires chauffeurs** lui donne une seule ligne.
9. **Configuration → Habilitations** : trois documents par chauffeur, un de chaque type — Permis, Visite médicale, Formation — avec une date d'expiration **au moins égale au jour du départ**. Sans les trois, le bouton Affecter est refusé.
10. **Configuration → Points de contrôle** : quatre points critiques sont livrés (pneus, huile, feux, freins). Vous pouvez en ajouter. Au passage en Embarquement, le départ reçoit une ligne par point actif.

Paramètres de ligne utiles :

- **Réserve entreprise** et **Libération (heures avant le départ)**. Jusqu'à cette heure, les places individuelles libres valent `capacité − places prises − max(0, réserve − places entreprise déjà prises)`. Après, l'invendu entreprise revient aux particuliers. Une navette `b2b` n'apparaît pas sur la page publique.
- **Annulation (heures avant le départ)** et **Remboursement (%)**. Le passager annule lui-même seulement avant cette limite, et seulement pour la part remboursée. Le guichet peut annuler après, sans remboursement. La fermeture d'une journée rembourse 100 % des billets payés de ce jour, même hors délai.

## Paramètres système

Réglages → Technique → Paramètres système.

| Clé | Rôle |
| --- | --- |
| `transport.hold_minutes` | Durée de tenue d'une réservation faite au guichet, et durée d'une offre de liste d'attente. Défaut : `15`. La page publique prolonge la tenue jusqu'à l'heure réelle du départ, retard compris. Un retard annoncé ensuite repousse cette tenue. La tenue de guichet ne bouge pas. |
| `transport.qr_secret` | Secret HMAC des QR, des liens de paiement, des liens d'attente et des liens GPS. Créé tout seul au premier billet (`secrets.token_hex(32)`). **Ne le changez pas** après l'émission de billets : les QR déjà imprimés ne passeront plus au scan. |
| `transport.algeria_ops_ready` | Marqueur interne. Ne pas l'effacer si vous voulez garder l'exemple déjà créé. |
| `web.base.url` | Adresse réelle du serveur, avec `https://` en production. Les liens des e-mails partent de cette valeur. |

## Vie d'un départ

Statuts, dans cet ordre, sans retour en arrière :

`Planifié → Affecté → Embarquement → En course → Terminé`

`Annulé` est possible seulement depuis Planifié, Affecté ou Embarquement, et seulement s'il ne reste ni billet confirmé ni passager embarqué. Les tenues ouvertes et la liste d'attente sont annulées avec le départ.

- **Affecter** : bus + chauffeur + trois habilitations valides le jour du service. La capacité du départ ne peut pas dépasser les sièges du bus.
- **Affecter automatiquement** : choisit le bus et le chauffeur selon la section suivante. Seulement depuis Planifié.
- **Ouvrir l'embarquement** : crée la checklist.
- **Démarrer** : les quatre contrôles critiques (et tout autre point critique, y compris un point ajouté après l'ouverture de l'embarquement) doivent être `Conforme`. Sinon le départ reste à quai.
- **Terminer** : seulement depuis En course.
- En course, terminé ou annulé : bus, chauffeur, capacité, réserve, heure et libération sont figés.
- Carburant, péage et chauffeur restent saisissables après Terminé. Ils sont bloqués sur Annulé.
- Un retard de 0 à 720 minutes est possible tant que le départ n'est pas terminé ou annulé. Les passagers qui ont un e-mail reçoivent le modèle « Retard » ou « Horaire rétabli », mis en file.
- **Changer le bus** : seulement Affecté ou Embarquement. Un siège déjà vendu au-dessus du nombre de places du nouveau bus est refusé.

Les dossiers du menu **Exploitation → Départs** :

- **Aujourd'hui** : `service_date` égale au jour de l'utilisateur. C'est aussi le menu parent Départs.
- **À venir** : date de service strictement après aujourd'hui.
- **Archivés** : date de service strictement avant aujourd'hui.

`service_date` est le jour local de l'heure réelle, retard compris. Un départ de 23:40 retardé de 40 minutes passe au lendemain. Fuseau : fuseau de l'utilisateur, sinon fuseau du contact de la société, sinon `Africa/Algiers`. L'horaire type est lu dans le même ordre.

## Affectation automatique

Le bouton **Affecter automatiquement** sur un départ planifié, le même bouton sur une sélection de départs, ou **Affecter les départs à venir** sur la ligne, choisit le bus et le chauffeur. Le bouton **Affecter** reste le choix manuel.

La longueur est la somme des kilomètres de la ligne. **Longueur imposée** remplace ce calcul.

| Longueur | Distance | Bus |
| --- | --- | --- |
| Court | moins de 160 km | Petit : 25 places ou moins |
| Moyen | de 160 km à moins de 300 km | Moyen : de 26 à 44 places |
| Long | 300 km et plus | Grand : 45 places et plus |

Le bus retenu a au moins la capacité du départ, et son créneau ne chevauche pas un autre départ non annulé. La durée du trajet est la distance divisée par la vitesse moyenne.

Chaque chauffeur a un seul itinéraire : onglet **Chauffeurs** de la ligne, ou **Configuration → Itinéraires chauffeurs**. S'il a conduit le même horaire la veille et qu'un collègue de la ligne est libre, le collègue prend le départ. Un chauffeur ne dépasse pas 8 h de conduite le même jour, et il ne peut pas être sur deux cars en même temps. Les trois habilitations doivent couvrir le jour de service. Un trajet plus long que 8 h ne s'affecte pas.

L'exemple pose quatre itinéraires : Karim Boudiaf sur Alger – Oran, Amina Cherif sur Alger – Constantine, Yacine Meziane sur Oran – Tlemcen, Sarah Belkacem sur la navette Alger – Tizi Ouzou. Une ligne courte qui vend plus de places qu'un petit bus n'a pas d'affectation automatique tant que **Longueur imposée** n'est pas choisie.

## Page publique

Le module Site web n'est pas requis. Les pages sont des contrôleurs HTTP.

| Adresse | Usage |
| --- | --- |
| `/reserver-un-billet` | Choix de la ligne, du jour, de la montée, de la descente, du plan de sièges. |
| `/reserver-un-billet/envoyer` | POST. Crée la tenue et ouvre le paiement. |
| `/reserver-un-billet/paiement/<id>/<jeton>` | Paiement et reçu. Le jeton fait 24 caractères hexadécimaux. |
| `/reserver-un-billet/annuler/<id>/<jeton>` | POST. Annulation passager, dans le délai de la ligne. |
| `/reserver-un-billet/retrouver` | Référence (`RES/2026/0001`) + téléphone. |
| `/reserver-un-billet/attente` | POST. Liste d'attente, seulement si le trajet affiche 0 place. |
| `/reserver-un-billet/attente/<id>/<jeton>` | Prendre la place proposée, puis payer. |
| `/suivi-bus/<id>/<jeton>` | Carte du dernier point reçu du GPS du bus. Lecture seule. |

**Plusieurs bases sur le même Odoo.** Si `odoo.conf` n'a pas `db_name` et que `dbfilter` laisse passer plus d'une base, chaque URL publique doit finir par `?db=NOM_DE_LA_BASE`. Le bouton **Suivi GPS** ajoute déjà `?db=`. Le menu **Réserver un billet** pointe vers `/reserver-un-billet` sans nom de base : ajoutez `?db=` à la main dans ce cas. Avec une seule base, le paramètre est inutile.

La page publique :

- cache les lignes de type Navette entreprise ;
- refuse un départ dont l'heure réelle, retard compris, est atteinte, ainsi qu'un départ annulé, en course ou terminé ;
- demande un nom d'au moins 2 caractères et un téléphone d'au moins 6 caractères ;
- vend de 1 à 8 places ;
- exige un tarif pour le couple d'arrêts ;
- dessine le car du bus (ou de la ligne) : pris en gris, choisi en teal, porte et coffre ne sont pas des sièges, chauffeur à gauche ;
- si plusieurs places, demande un nom par siège. Un nom vide devient « Passager N » ;
- affiche l'heure de passage de chaque arrêt.

Le téléphone de recherche ignore espaces, `+213` et les zéros de tête : `+213555123456` et `0555123456` sont la même clé.

## Paiement

La page de paiement **confirme le billet dans Odoo et télécharge le reçu**. Elle n'appelle aucune banque. Ne demandez pas le numéro de carte ni le CVV. Il n'y a pas de clé marchand à configurer.

- En ligne : référence `PAY-<id réservation>`, mode `online`.
- Guichet espèces : bouton **Encaisser**, référence `ESP-<id>`.
- Guichet TPE : bouton **Encaisser**, référence `TPE-<id>`.
- Un billet déjà payé ne change pas de mode.
- L'abonné entreprise se confirme sans encaissement.

Le reçu, le billet et le manifeste sont des PDF QWeb. Le CSS force **Arial** (`transport.report_font`), parce que la police Lato d'Odoo s'imprime mal avec wkhtmltopdf sous Windows. Un PDF déjà téléchargé garde l'ancienne police : il faut le régénérer.

Sans wkhtmltopdf, Odoo rend souvent du HTML à la place du PDF. Le passager doit recevoir un fichier PDF.

## Conditions du GPS et du lecteur fixés dans le bus

Ces conditions sont toutes obligatoires. Si une seule manque, le bus n'envoie rien, ou Odoo refuse le point et le passage.

1. **Le GPS appelle une adresse HTTP.** Le boîtier doit savoir faire un GET ou un POST vers l'adresse copiée sur la fiche du bus, et y ajouter la latitude et la longitude. Les noms acceptés sont `lat` ou `latitude`, et `lon`, `lng` ou `longitude`. Un GPS qui ne parle qu'un protocole binaire (trame Teltonika, GT06, SMS seul) ne joint pas Odoo tant qu'un boîtier intermédiaire ne traduit pas cet appel.
2. **Le lecteur de porte appelle une adresse HTTP.** Il doit envoyer le texte lu du QR, pas seulement l'image. Le texte part dans `payload`, `code`, `qr` ou `data`. Un lecteur qui se contente d'afficher le QR sur un écran, sans requête HTTP, ne passe pas le passager.
3. **Odoo n'ouvre pas le portillon.** Le logiciel répond. Le boîtier du lecteur ouvre le passage seulement quand le code HTTP est **200**. Tout autre code (`404`, `409`) laisse le passage fermé. Ce branchement se règle dans le lecteur, pas dans Odoo.
4. **Chaque bus a son jeton.** Sur Flotte → Véhicules, le champ **Jeton du boîtier** contient 32 caractères hexadécimaux, créés à l'enregistrement du bus. L'adresse GPS et l'adresse du lecteur contiennent ce jeton. Deux bus n'ont jamais le même.
5. **Le jeton est le seul mot de passe.** Il n'y a pas de login. Qui possède l'adresse peut envoyer une position ou un scan. Ne la mettez pas sur la page de vente, ni dans un PDF public.
6. **`web.base.url` est l'adresse que le bus peut joindre.** Réglages → Technique → Paramètres système, clé `web.base.url`. En production elle commence par `https://` et c'est le nom public du serveur. Les deux adresses affichées sur la fiche du bus sont construites avec cette valeur. Si elle vaut `http://localhost:8019`, elles ne marchent que sur l'ordinateur du serveur. Un bus sur la route ne résout pas `localhost`.
7. **Le nom de la base est dans l'adresse.** La forme complète est `https://serveur/bus/<jeton>/position?db=<base>` et `https://serveur/bus/<jeton>/scan?db=<base>`. Le `?db=` est obligatoire tant que `odoo.conf` n'a pas un `db_name` unique. Copiez l'adresse affichée sur la fiche, ne la retapez pas de mémoire.
8. **Chaque bus a un réseau vers ce serveur.** Une carte SIM ou un routeur 4G dans le car. Odoo n'appelle jamais le GPS ni le lecteur. Il attend leur requête. Si le réseau tombe au moment du point, le boîtier doit renvoyer plus tard. Un point non envoyé n'existe pas.
9. **Le scan exige un départ ouvert. Le GPS, non.** Le lecteur ne passe un passager que si ce bus est affecté à un départ en **Embarquement** ou **En course**. S'il y a les deux, le départ **En course** reçoit le scan. Sinon le lecteur répond `409` : « Ce bus n'a pas de départ en embarquement ou en course. » Le GPS, lui, enregistre toujours le point sur la fiche du bus. S'il existe un départ ouvert, le même point est aussi copié sur ce départ.
10. **Le QR est celui imprimé par Odoo.** Le texte exact est `TRP:<id réservation>:<20 caractères hex>`. La signature se vérifie avec le paramètre `transport.qr_secret`. Ne changez pas ce secret après avoir imprimé des billets : les QR déjà sortis seront refusés.
11. **Le billet est confirmé, payé s'il est individuel, et il est pour ce départ.** L'abonné entreprise passe sans encaissement. Le billet individuel non payé reçoit `409` : « Ce billet individuel n'est pas payé. » Un billet en attente, annulé, déjà embarqué, ou prévu sur un autre départ reçoit aussi `409`, et le portillon reste fermé. Le second passage du même QR est refusé, parce que le billet n'est plus « confirmé ».
12. **La carte de l'administration a besoin d'Internet sur l'écran du bureau.** Le bouton **Suivi GPS** charge Leaflet et les tuiles OpenStreetMap. Cela n'a rien à voir avec le réseau du bus. Sans ces tuiles, le point est quand même enregistré, la carte reste vide.

## Scan des billets

Le lecteur fixé devant la porte du bus envoie le texte du QR à Odoo. Le chauffeur ne tient pas de téléphone. Odoo ne commande pas le moteur du portillon : le boîtier du lecteur doit ouvrir le passage quand la réponse HTTP est **200**, et le refuser pour tout autre code.

1. Sur la fiche du bus (Flotte → Véhicules), copier **Adresse du lecteur**. Elle a la forme `https://serveur/bus/<jeton de 32 hex>/scan?db=<base>`.
2. Dans le lecteur, configurer cette adresse. Le texte lu du QR part dans `payload`, `code`, `qr` ou `data`, en GET ou en POST. Le jeton identifie le bus. Il ne faut pas de login.
3. Le bus doit avoir un départ en **Embarquement** ou **En course**, avec ce véhicule affecté. S'il est en course, c'est ce départ qui reçoit le scan. Sinon, c'est le départ en embarquement.
4. Le QR imprimé vaut exactement `TRP:<id réservation>:<20 caractères hex>`. Odoo vérifie la signature avec `transport.qr_secret`.
5. Réponse `200` et le nom du passager : le billet passe à Embarqué. Le boîtier peut ouvrir le portillon et afficher le nom.
6. Réponse `409` : le texte de l'erreur (billet refusé, autre départ, annulé, non confirmé, bus sans départ ouvert). Le portillon reste fermé.
7. Réponse `404` et « Bus inconnu. » : le jeton n'est pas celui d'un bus.

Le bus a besoin d'un accès réseau jusqu'au serveur (routeur 4G). `web.base.url` doit être l'adresse que le bus peut joindre, en `https://` en production. `localhost` ne marche que sur la machine du serveur.

Le bouton **Scanner un billet** du départ reste utilisable sans lecteur fixe : il ouvre la caméra d'un téléphone, ou un champ pour une douchette clavier. Ce n'est pas le portillon.

Refus, avec le message exact du logiciel :

- signature inconnue ou texte modifié : « Billet refusé. »
- autre départ : « Ce billet est pour un autre départ. »
- billet annulé : « Ce billet est annulé. »
- réservation pas encore confirmée : « Seul un billet confirmé s'embarque. »
- départ encore Planifié ou Affecté : « L'embarquement n'est pas ouvert sur ce départ. »

Un QR se crée à la confirmation et ne se réécrit pas. Un second scan d'un passager déjà embarqué échoue, parce que la réservation n'est plus « confirmée ».

Le manifeste (bouton d'impression du départ) a une ligne par siège : numéro, nom, canal, montée, descente, statut.

## GPS

Le GPS fixé dans le bus envoie sa position tout seul. Le chauffeur n'appuie sur rien.

1. Sur la fiche du bus, copier **Adresse GPS**. Elle a la forme `https://serveur/bus/<jeton de 32 hex>/position?db=<base>`.
2. Dans le boîtier, mettre cette adresse et lui faire ajouter la latitude et la longitude. Les noms acceptés sont `lat` ou `latitude`, et `lon`, `lng` ou `longitude`. Exemple : l'adresse suivie de `&lat=36.7538&lon=3.0588`. GET, POST formulaire ou JSON conviennent.
3. Le point est toujours enregistré sur la fiche du bus. S'il y a un départ **En course**, ou à défaut **Embarquement**, le même point y est copié. Les deux fiches montrent la dernière latitude, la dernière longitude et l'heure.
4. Réponse `200` et `ok` : le point est enregistré, même sans départ ouvert. `409` : coordonnées illisibles ou hors limites (−90..90, −180..180). `404` : jeton inconnu.
5. Le même réseau 4G que le lecteur de porte suffit. Sans réseau au moment du point, le boîtier doit renvoyer plus tard : Odoo ne va pas chercher le GPS, il attend l'appel.
6. Le bouton **Suivi GPS** du départ ouvre seulement la carte du dernier point déjà reçu (Leaflet et OpenStreetMap, donc Internet côté écran de l'administration). Personne n'envoie une position depuis cette page.

Le jeton du bus est secret. Qui l'a peut envoyer une fausse position ou un scan. Ne le mettez pas sur la page de vente.

## Liste d'attente

Le bouton public n'apparaît que lorsque le trajet affiche 0 place libre. L'inscription crée `ATT/année/....`.

Une seule offre active par départ. Elle va à la première personne en attente dont le nombre de places tient dans le libre individuel (la réserve entreprise reste protégée). L'offre dure `transport.hold_minutes`. Le cron **Transport : libérer les réservations expirées** tourne toutes les 5 minutes : il annule les tenues échues, expire les offres en retard, puis propose la place suivante. Odoo doit rester démarré pour que le cron parte.

Prendre l'offre crée une réservation en attente. La place n'est confirmée qu'au paiement.

## E-mails

Modèles, tous mis en file (`force_send=False`) :

- billet émis, s'il y a une adresse ;
- retard et horaire rétabli ;
- report de billet ;
- offre de liste d'attente ;
- fermeture de journée.

Sans serveur de courrier sortant (Réglages → Technique → Serveurs de courrier sortant) et sans le cron de la file mail, le message reste dans Odoo. Réglez `web.base.url` avant d'envoyer, sinon les liens pointent vers `localhost`.

## Résultat, statistiques, relevé

- Onglet **Résultat** du départ : places vendues (confirmées, embarquées, no-show), encaissé, remboursé, taux de remplissage par tronçon, carburant, péage, chauffeur, marge. La marge vaut encaissé − remboursé − coûts.
- **Exploitation → Statistiques** : sur une période, par ligne, places vendues, places offertes, remplissage, attente, marge, principal trajet. Le profit de la période est la somme des marges des départs non annulés.
- Les propositions lisent ces chiffres. Elles n'appellent aucun modèle externe. Remplissage ≥ 75 % ou au moins 2 personnes en attente : proposer un départ de plus sur le trajet le plus vendu. Remplissage ≤ 40 % et un bus de la flotte qui couvre le pic vendu avec moins de sièges que la ligne : proposer ce bus. Aucune proposition n'invente une ligne jamais vendue.
- **Entreprises → Relevé mensuel**, ou le bouton **Relevé** du contrat : PDF des trajets abonnés confirmés, embarqués ou no-show sur la période. Le pied de page dit que ce n'est pas une facture.

## Fermer une journée

**Exploitation → Fermer une journée**, ou le bouton sur la ligne. Motif obligatoire. Ligne vide = toutes les lignes.

Le jour choisi annule les départs Planifié, Affecté et Embarquement. Les billets payés de ces départs sont remboursés en totalité. La liste d'attente de ces départs est annulée. Un départ **En course** reste. Un départ qui a déjà un passager embarqué est conservé. Les autres jours ne bougent pas.

## Séquences

| Document | Forme |
| --- | --- |
| Départ | `DEP/2026/0001` |
| Réservation | `RES/2026/0001` |
| Contrat | `CTR/2026/0001` |
| Liste d'attente | `ATT/2026/0001` |

## Dépannage court

| Symptôme | Cause la plus fréquente |
| --- | --- |
| Pas de menu Transport | L'utilisateur n'a pas Dispatch ou Responsable. |
| « Ce trajet n'a pas de prix. » | Pas de tarif pour cette montée et cette descente. |
| Affecter refusé | Bus, chauffeur, ou une des trois habilitations manquante ou expirée avant le jour du départ. |
| Affecter automatiquement refusé | Pas de distance sur la ligne, pas de chauffeur sur cet itinéraire, aucun bus de la bonne taille avec assez de places libre, chauffeur déjà en course, ou plus de 8 h de conduite ce jour-là. |
| Démarrer refusé | Un contrôle critique n'est pas Conforme. |
| Le QR ne passe pas | Texte incomplet, autre départ, billet non confirmé, ou `transport.qr_secret` changé. |
| La caméra ne s'ouvre pas | Page ouverte en HTTP depuis un autre appareil, ou autorisation refusée. Le champ QR reste utilisable. Passez en HTTPS. |
| Le boîtier n'envoie pas le GPS | L'adresse copiée sur le bus n'est pas joignable, le jeton est faux, ou les paramètres ne s'appellent pas `lat`/`lon`. |
| Carte vide | Pas d'Internet vers unpkg ou OpenStreetMap, ou aucune position envoyée. |
| PDF avec des lettres illisibles | Ancien PDF, ou wkhtmltopdf absent. Régénérez après la mise à jour. La police forcée est Arial. |
| E-mail jamais reçu | Pas de serveur sortant, ou pas d'adresse sur le passager. |
| Page publique demande la base | Ajoutez `?db=NOM_DE_LA_BASE`. |
| Les départs d'hier sont dans Aujourd'hui | Mettez à jour le module. Le filtre est `service_date`, pas l'ancien filtre « ouvert ». |

---

# English

## What this module does

One operation, two sales channels.

- **Individual ticket**: the passenger books on the public page, pays on the company page, and downloads a PDF receipt plus a QR ticket.
- **Company subscriber**: the counter confirms a seat on a contract. The subscriber does not pay at the counter. The monthly statement lists the trips. That statement is not an accounting invoice.

Seats are counted per leg. A passenger travelling Algiers → Blida occupies every leg up to Blida. After Blida, the same seat number can be sold again.

Collected amount, refunds, fuel, tolls, driver cost, and margin stay on the departure. The module does not create an `account.move`. It does not depend on Accounting, Sales, Website, or Payment.

## What must be installed

| Item | Requirement |
| --- | --- |
| Odoo | 19.0. The module uses `models.Constraint`, `<list>` views, and `<chatter/>`. |
| Python | 3.10 or newer. This environment uses 3.13. |
| PostgreSQL | A dedicated database. The database user must be allowed to create tables. |
| Odoo modules | `base`, `mail`, `fleet`, `hr`. Odoo installs them together with Transport. |
| Python package `qrcode` | Required. The ticket QR is a PNG. Without this package, issuing a ticket crashes. |
| Python package `Pillow` | Required. `qrcode` writes the PNG through Pillow. ReportLab is not used for the QR. |
| wkhtmltopdf | Required for a real PDF (ticket, receipt, manifest, statement). Odoo 19 expects 0.12.6 with the patched Qt. On Windows the usual binary is `C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe`. |
| Fixed GPS tracker and door reader | Required for automatic position and boarding. See the GPS and Scan sections. |
| Internet on the office screen | Required for the Leaflet map. The bus only needs HTTP access to the server. |
| Outgoing mail server | Optional for selling. Required if messages must actually leave Odoo. |
| CIB, BaridiMob, or SATIM gateway | Not included. There is nothing to configure. |

Install the Python packages in the Odoo virtualenv:

```bash
pip install "qrcode" "Pillow"
```

The addon directory must be named `transport` and must sit on `addons_path`:

```ini
[options]
addons_path = /path/to/odoo/addons,/path/to/custom_addons
db_host = localhost
db_port = 5432
db_user = odoo
db_password = REPLACE
http_port = 8069
```

Do not commit the database password.

Install:

```bash
python odoo-bin -c odoo.conf -d DATABASE -i transport --stop-after-init
```

Upgrade after a code change:

```bash
python odoo-bin -c odoo.conf -d DATABASE -u transport --stop-after-init
```

Restart Odoo and open the database. The **Transport** menu is visible to a user who has the Transport privilege.

Run the module tests on a throwaway database, never on the passenger database:

```bash
python odoo-bin -c odoo.conf -d transport_ci -u transport --test-enable --test-tags /transport --stop-after-init --http-port=8071 --log-level=test
```

The expected ending is `0 failed, 0 error(s)`.

## Users

Settings → Users → privilege **Transport**.

- **Dispatch**: departures, bus, driver, bookings, scan, counter payment, GPS, statistics, statement.
- **Responsable** (manager): everything in Dispatch, plus lines, stops, schedules, contracts, and check points.

The Odoo administrator receives **Responsable** at install. An internal user without the privilege does not see the menu. Passengers have no user account: public pages use `auth='public'`.

## Network loaded at install

| Code | Line | Type | Seat plan |
| --- | --- | --- | --- |
| ALG-MED | Algiers – Médéa | Hybrid | Coach 2+2, rear bench of 5 |
| ALG-ORN | Algiers – Oran | Hybrid | Front door, 2+2, rear bench of 5 |
| ALG-CON | Algiers – Constantine | Intercity | Courier seat, then 2+2 |
| ALG-TIZ | Algiers – Tizi Ouzou shuttle | Company | Minibus 2+1, bench of 4. Hidden on the public page. |
| ORN-TLM | Oran – Tlemcen | Hybrid | Coach 2+2, rear bench of 5 |
| CON-ANN | Constantine – Annaba | Intercity | Coach 2+2 all the way back |
| ALG-BEJ | Algiers – Béjaïa | Hybrid | Midibus 2+2, rear trunk |

Operational decoration (sample contracts, departures, tickets) runs once, marked by `transport.algeria_ops_ready`. A later `-u transport` does not run it again. Sequences and mail templates are `noupdate="1"`: editing the XML does not update a database that already has them.

You can ignore this network and build your own. A line sells only when the next section is complete. A missing fare stops the sale with "Ce trajet n'a pas de prix."

## Minimum setup for a line that sells

1. **Stops**, each with a unique code.
2. **Line**: code, type, capacity, seat layout, average speed (default 70 km/h).
3. **Stops on the line**, in order. Distance is kilometres **from the previous stop**. Passage time is that distance divided by speed. A delay shifts every stop by the same number of minutes.
4. **A fare for each boarding / alighting pair**, on the Fares tab. "End-to-end price" is only a hint. The public page does not use it.
5. **Schedule**: weekdays and time.
6. **Operations → Generate departures**, for a date range.
7. **Fleet → Vehicles**: a bus with a seat count and a layout. The vehicle layout replaces the line layout when it contains exactly the departure capacity. Otherwise the departure keeps the line layout, then falls back to `coach_2_2`.
8. **Employees**: the driver is an `hr.employee` of the same company. **Configuration → Driver routes** gives that driver one line.
9. **Configuration → Qualifications**: three documents per driver, one of each type — licence, medical visit, training — with an expiry date **on or after the service day**. Assign is refused while any of the three is missing.
10. **Configuration → Check points**: four critical points ship with the module (tyres, oil, lights, brakes). You can add more. Opening boarding copies every active point onto the departure.

Useful line settings:

- **Company reserve** and **Release (hours before departure)**. Until that time, free individual seats are `capacity − taken − max(0, reserve − company seats already booked)`. After that, unsold company seats go back to individuals. A `b2b` shuttle does not appear on the public page.
- **Cancellation (hours before departure)** and **Refund (%)**. The passenger can cancel only before that limit, and only for the refunded share. Staff can cancel later, with no refund. Closing a service day refunds 100% of paid tickets for that day, even outside the window.

## System parameters

Settings → Technical → System Parameters.

| Key | Role |
| --- | --- |
| `transport.hold_minutes` | How long a counter booking is held, and how long a waitlist offer lasts. Default: `15`. The public page extends the hold until the real departure time, delay included. A delay announced later pushes that hold. A counter hold does not move. |
| `transport.qr_secret` | HMAC secret for QR codes, payment links, waitlist links, and GPS links. Created automatically on the first ticket (`secrets.token_hex(32)`). **Do not change it** after tickets exist: already printed QR codes will fail the scan. |
| `transport.algeria_ops_ready` | Internal marker. Leave it if you want to keep the sample data already created. |
| `web.base.url` | The real server address, with `https://` in production. Mail links are built from this value. |

## Life of a departure

States move forward only:

`Planned → Assigned → Boarding → On the road → Done`

`Cancelled` is allowed only from Planned, Assigned, or Boarding, and only when no confirmed ticket and no boarded passenger remain. Open holds and the waitlist are cancelled with the departure.

- **Assign**: bus + driver + three qualifications valid on the service day. Departure capacity cannot exceed the bus seat count.
- **Assign automatically**: picks the bus and the driver using the next section. Planned departures only.
- **Open boarding**: creates the checklist.
- **Start**: every critical check (the four shipped ones and any you added, including a point added after boarding was opened) must be OK. Otherwise the bus stays at the stop.
- **Done**: only from On the road.
- On the road, done, or cancelled: vehicle, driver, capacity, reserve, time, and release are frozen.
- Fuel, toll, and driver cost can still be entered after Done. They are blocked on Cancelled.
- A delay of 0 to 720 minutes is allowed until the departure is done or cancelled. Passengers with an email get the "Delay" or "Schedule restored" template, queued.
- **Swap the bus**: Assigned or Boarding only. A seat number already sold above the replacement seat count is refused.

**Operations → Departures** folders:

- **Today**: `service_date` equals the user's today. This is also the parent Departures menu.
- **Upcoming**: service date strictly after today.
- **Archived**: service date strictly before today.

`service_date` is the local day of the real departure, delay included. A 23:40 departure delayed by 40 minutes moves to the next day. Timezone: the user's timezone, otherwise the company contact timezone, otherwise `Africa/Algiers`. A schedule is read in that same order.

## Automatic assignment

**Assign automatically** on a planned departure, the same button on a selection of departures, or **Affecter les départs à venir** on the line, picks the bus and the driver. **Assign** remains the manual choice.

Length is the sum of the line's kilometres. **Longueur imposée** replaces that calculation.

| Length | Distance | Bus |
| --- | --- | --- |
| Short | under 160 km | Small: 25 seats or fewer |
| Medium | from 160 km up to, but not including, 300 km | Medium: 26 to 44 seats |
| Long | 300 km and more | Large: 45 seats and more |

The chosen bus has at least the departure capacity, and its time window does not overlap another departure that is not cancelled. Trip duration is distance divided by average speed.

Each driver has one route: the line's **Chauffeurs** tab, or **Configuration → Itinéraires chauffeurs**. If that driver ran the same schedule yesterday and a colleague on the line is free, the colleague takes the departure. A driver does not exceed 8 driving hours on the same day, and cannot be on two coaches at once. The three qualifications must cover the service day. A trip longer than 8 hours is not assigned.

The sample creates four routes: Karim Boudiaf on Algiers – Oran, Amina Cherif on Algiers – Constantine, Yacine Meziane on Oran – Tlemcen, Sarah Belkacem on the Algiers – Tizi Ouzou shuttle. A short line that sells more seats than a small bus has no automatic assignment until **Longueur imposée** is set.

## Public pages

The Website module is not required. These are HTTP controllers.

| Path | Use |
| --- | --- |
| `/reserver-un-billet` | Line, day, boarding stop, alighting stop, seat map. |
| `/reserver-un-billet/envoyer` | POST. Creates the hold and opens payment. |
| `/reserver-un-billet/paiement/<id>/<token>` | Payment and receipt. The token is 24 hex characters. |
| `/reserver-un-billet/annuler/<id>/<token>` | POST. Passenger cancellation, inside the line's window. |
| `/reserver-un-billet/retrouver` | Reference (`RES/2026/0001`) + phone. |
| `/reserver-un-billet/attente` | POST. Waitlist, only when the trip shows 0 seats. |
| `/reserver-un-billet/attente/<id>/<token>` | Take the offered seat, then pay. |
| `/suivi-bus/<id>/<token>` | Map of the last point received from the bus GPS. Read only. |

**Several databases on one Odoo.** If `odoo.conf` has no `db_name` and `dbfilter` allows more than one database, every public URL needs `?db=DATABASE`. The **GPS tracking** button already adds `?db=`. The **Book a ticket** menu points at `/reserver-un-billet` without a database name: add `?db=` yourself in that case. With a single database, the parameter is unnecessary.

The public page:

- hides company-shuttle lines;
- refuses a departure whose real time, delay included, has been reached, and a departure that was cancelled, is on the road, or is done;
- requires a name of at least 2 characters and a phone of at least 6 characters;
- sells 1 to 8 seats;
- requires a fare for that stop pair;
- draws that bus (or the line) : taken seats grey, selected seats teal, door and trunk are not seats, driver on the left;
- asks for one name per seat when more than one seat is chosen. An empty extra name becomes "Passager N";
- shows the passage time of every stop.

Phone lookup ignores spaces, `+213`, and leading zeros: `+213555123456` and `0555123456` are the same key.

## Payment

The payment page **confirms the ticket in Odoo and downloads the receipt**. It does not call a bank. Do not ask for the card number or the CVV. There is no merchant key to set.

- Online: reference `PAY-<booking id>`, method `online`.
- Counter cash: **Collect** button, reference `ESP-<id>`.
- Counter card terminal: **Collect** button, reference `TPE-<id>`.
- An already paid ticket cannot change method.
- A company subscriber is confirmed without collection.

Receipt, ticket, and manifest are QWeb PDFs. CSS forces **Arial** (`transport.report_font`), because Odoo's Lato font prints badly with wkhtmltopdf on Windows. A PDF already downloaded keeps the old font: generate it again.

Without wkhtmltopdf, Odoo often returns HTML instead of a PDF. The passenger should receive a PDF file.

## Conditions for the GPS and the reader fixed in the bus

Every condition below is required. If one is missing, the bus sends nothing, or Odoo refuses the point and the passage.

1. **The GPS calls an HTTP address.** The tracker must GET or POST the address copied from the bus form, and add latitude and longitude. Accepted names are `lat` or `latitude`, and `lon`, `lng`, or `longitude`. A GPS that only speaks a binary protocol (Teltonika frame, GT06, SMS only) does not reach Odoo until a box in between translates that call.
2. **The door reader calls an HTTP address.** It must send the text read from the QR, not only the picture. The text goes in `payload`, `code`, `qr`, or `data`. A reader that only shows the QR on a screen, with no HTTP request, does not board the passenger.
3. **Odoo does not open the gate.** The software answers. The reader box opens the passage only when the HTTP status is **200**. Any other status (`404`, `409`) leaves the passage shut. That wiring is set on the reader, not in Odoo.
4. **Each bus has its own token.** On Fleet → Vehicles, **Jeton du boîtier** holds 32 hexadecimal characters, created when the bus is saved. The GPS address and the reader address contain this token. Two buses never share it.
5. **The token is the only password.** There is no login. Whoever has the address can post a position or a scan. Do not put it on the booking page, or in a public PDF.
6. **`web.base.url` is the address the bus can reach.** Settings → Technical → System Parameters, key `web.base.url`. In production it starts with `https://` and is the public name of the server. Both addresses shown on the bus form are built from this value. If it is `http://localhost:8019`, they work only on the server computer. A bus on the road does not resolve `localhost`.
7. **The database name is part of the address.** The full form is `https://server/bus/<token>/position?db=<database>` and `https://server/bus/<token>/scan?db=<database>`. The `?db=` is required while `odoo.conf` has no single `db_name`. Copy the address shown on the form. Do not retype it from memory.
8. **Each bus has a network path to that server.** A SIM card or a 4G router in the coach. Odoo never calls the GPS or the reader. It waits for their request. If the network drops at the moment of the point, the box must send it again later. A point that was not sent does not exist.
9. **The scan needs an open departure. The GPS does not.** The reader boards a passenger only when this bus is assigned to a departure in **Boarding** or **On the road**. If both exist, the departure **On the road** receives the scan. Otherwise the reader answers `409`: "Ce bus n'a pas de départ en embarquement ou en course." The GPS always stores the point on the bus form. When an open departure exists, the same point is also copied onto that departure.
10. **The QR is the one printed by Odoo.** The exact text is `TRP:<booking id>:<20 hex characters>`. The signature is checked with the parameter `transport.qr_secret`. Do not change that secret after tickets have been printed: QR codes already issued will be refused.
11. **The ticket is confirmed, paid when it is an individual ticket, and it belongs to this departure.** A company subscriber passes without counter payment. An unpaid individual ticket gets `409`: "Ce billet individuel n'est pas payé." A ticket on hold, cancelled, already boarded, or booked on another departure also gets `409`, and the gate stays shut. A second pass of the same QR is refused, because the ticket is no longer "confirmed".
12. **The admin map needs Internet on the office screen.** The **Suivi GPS** button loads Leaflet and the OpenStreetMap tiles. That is separate from the bus network. Without those tiles the point is still stored, and the map stays empty.

## Ticket scan

The reader fixed at the bus door sends the QR text to Odoo. The driver does not hold a phone. Odoo does not drive the gate motor: the reader box must open the gate when the HTTP status is **200**, and keep it shut for any other status.

1. On the bus form (Fleet → Vehicles), copy **Adresse du lecteur**. It looks like `https://server/bus/<32 hex token>/scan?db=<database>`.
2. Configure the reader with that address. The QR text is sent as `payload`, `code`, `qr`, or `data`, by GET or POST. The token identifies the bus. No login.
3. The bus must have a departure in **Boarding** or **On the road**, with this vehicle assigned. A departure on the road wins. Otherwise the boarding departure receives the scan.
4. The printed QR is exactly `TRP:<booking id>:<20 hex characters>`. Odoo checks the signature with `transport.qr_secret`.
5. Status `200` and the passenger name: the ticket becomes Boarded. The box can open the gate and show the name.
6. Status `409`: the error text (refused ticket, other departure, cancelled, not confirmed, bus with no open departure). The gate stays shut.
7. Status `404` and "Bus inconnu.": the token is not a bus token.

The bus needs a network path to the server (a 4G router). `web.base.url` must be the address the bus can reach, `https://` in production. `localhost` works only on the server machine.

The departure button **Scanner un billet** still works without a fixed reader: it opens a phone camera, or a field for a keyboard wedge. That is not the gate.

Refusals, with the software's own message:

- unknown signature or edited text: "Billet refusé."
- another departure: "Ce billet est pour un autre départ."
- cancelled ticket: "Ce billet est annulé."
- booking not confirmed yet: "Seul un billet confirmé s'embarque."
- departure still Planned or Assigned: "L'embarquement n'est pas ouvert sur ce départ."

A QR is created at confirmation and is never rewritten. Scanning a passenger who is already boarded fails, because the booking is no longer "confirmed".

The departure manifest prints one row per seat: number, name, channel, boarding stop, alighting stop, status.

## GPS

The GPS fixed in the bus sends its position by itself. The driver taps nothing.

1. On the bus form, copy **Adresse GPS**. It looks like `https://server/bus/<32 hex token>/position?db=<database>`.
2. Put that address in the tracker and have it append latitude and longitude. Accepted names are `lat` or `latitude`, and `lon`, `lng`, or `longitude`. Example: the address followed by `&lat=36.7538&lon=3.0588`. GET, form POST, or JSON all work.
3. The point is always stored on the bus form. If there is a departure **On the road**, or else **Boarding**, the same point is copied there. Both forms show the last latitude, last longitude, and time.
4. Status `200` and `ok`: the point is stored, even with no open departure. `409`: coordinates unreadable or out of range (−90..90, −180..180). `404`: unknown token.
5. The same 4G link as the door reader is enough. If the network is down at that moment, the tracker must send the point again later. Odoo does not call the GPS. It waits for the call.
6. The departure button **Suivi GPS** only opens the map of the last point already received (Leaflet and OpenStreetMap, so the admin screen needs Internet). Nobody sends a position from that page.

The bus token is a secret. Anyone who has it can post a fake position or a scan. Do not put it on the booking page.

## Waitlist

The public button appears only when the trip shows 0 free seats. Joining creates `ATT/year/....`.

One active offer per departure. It goes to the first waiting person whose seat count fits in the free individual seats (the company reserve stays protected). The offer lasts `transport.hold_minutes`. The cron **Transport : libérer les réservations expirées** runs every 5 minutes: it cancels expired holds, expires late offers, then offers the next person. Odoo must stay running for the cron to fire.

Claiming the offer creates a held booking. The seat is confirmed only when it is paid.

## Email

Templates, all queued (`force_send=False`):

- ticket issued, when an address exists;
- delay and schedule restored;
- ticket rebooked;
- waitlist offer;
- service-day closure.

Without an outgoing mail server (Settings → Technical → Outgoing Mail Servers) and without the mail queue cron, the message stays inside Odoo. Set `web.base.url` before sending, or the links point at `localhost`.

## Result, statistics, statement

- Departure **Result** tab: seats sold (confirmed, boarded, no-show), collected, refunded, fill rate per leg, fuel, toll, driver, margin. Margin is collected − refunded − costs.
- **Operations → Statistics**: for a period, per line, seats sold, seats offered, fill, waitlist, margin, main origin-destination. Period profit is the sum of margins of non-cancelled departures.
- Proposals read those figures. They do not call an external model. Fill ≥ 75% or at least 2 people waiting: suggest one more departure on the best-selling pair. Fill ≤ 40% and a fleet bus that covers the sold peak with fewer seats than the line: suggest that bus. A proposal never invents a route that was never sold.
- **Companies → Monthly statement**, or the **Statement** button on the contract: PDF of subscriber trips in confirmed, boarded, or no-show state for the period. The footer says it is not an invoice.

## Closing a service day

**Operations → Close a day**, or the button on the line. A reason is required. An empty line means every line.

The chosen day cancels Planned, Assigned, and Boarding departures. Paid tickets on those departures are refunded in full. Their waitlist is cancelled. A departure **On the road** stays. A departure that already has a boarded passenger is kept. Other days are left as they are.

## Sequences

| Document | Shape |
| --- | --- |
| Departure | `DEP/2026/0001` |
| Booking | `RES/2026/0001` |
| Contract | `CTR/2026/0001` |
| Waitlist | `ATT/2026/0001` |

## Short troubleshooting

| Symptom | Usual cause |
| --- | --- |
| No Transport menu | The user has neither Dispatch nor Responsable. |
| "Ce trajet n'a pas de prix." | No fare for that boarding and alighting pair. |
| Assign refused | Bus, driver, or one of the three qualifications missing or expired before the service day. |
| Automatic assignment refused | No distance on the line, no driver on that route, no free bus of the right size with enough seats, driver already on the road, or more than 8 driving hours that day. |
| Start refused | A critical check is not OK. |
| QR will not scan | Incomplete text, wrong departure, ticket not confirmed, or `transport.qr_secret` was changed. |
| The camera does not open | The page was opened over HTTP from another device, or permission was denied. The QR field still works. Use HTTPS. |
| The tracker sends no GPS | The address copied on the bus cannot be reached, the token is wrong, or the parameters are not named `lat`/`lon`. |
| Empty map | No Internet to unpkg or OpenStreetMap, or no position has been sent. |
| PDF letters look wrong | An old PDF, or wkhtmltopdf is missing. Generate it again after the upgrade. The forced font is Arial. |
| Email never arrives | No outgoing server, or the passenger has no address. |
| Public page asks which database | Add `?db=DATABASE`. |
| Yesterday's departures are under Today | Upgrade the module. The filter is `service_date`, not the old "open" filter. |

---

# Deutsch

## Was das Modul tut

Ein Betrieb, zwei Verkaufswege.

- **Einzelfahrschein**: der Fahrgast bucht auf der öffentlichen Seite, bezahlt auf der Seite der Gesellschaft und lädt einen PDF-Beleg plus einen QR-Fahrschein herunter.
- **Firmenabo**: der Schalter bestätigt den Platz auf einem Vertrag. Der Abonnent zahlt nicht am Schalter. Die Monatsaufstellung listet die Fahrten. Diese Aufstellung ist keine Buchhaltungsrechnung.

Sitze werden pro Teilstrecke gezählt. Ein Fahrgast Algier → Blida belegt alle Teilstrecken bis Blida. Danach kann dieselbe Sitznummer wieder verkauft werden.

Eingenommenes Geld, Erstattungen, Kraftstoff, Maut, Fahrerkosten und Marge bleiben an der Abfahrt. Das Modul erzeugt keine `account.move`. Es hängt nicht an Buchhaltung, Verkauf, Website oder Zahlung.

## Was installiert sein muss

| Teil | Pflicht |
| --- | --- |
| Odoo | 19.0. Das Modul nutzt `models.Constraint`, `<list>`-Ansichten und `<chatter/>`. |
| Python | 3.10 oder neuer. Diese Umgebung nutzt 3.13. |
| PostgreSQL | Eine eigene Datenbank. Der Datenbanknutzer muss Tabellen anlegen dürfen. |
| Odoo-Module | `base`, `mail`, `fleet`, `hr`. Odoo installiert sie zusammen mit Transport. |
| Python-Paket `qrcode` | Pflicht. Der QR des Fahrscheins ist ein PNG. Ohne das Paket bricht das Ausstellen ab. |
| Python-Paket `Pillow` | Pflicht. `qrcode` schreibt das PNG über Pillow. ReportLab wird für den QR nicht benutzt. |
| wkhtmltopdf | Pflicht für ein echtes PDF (Fahrschein, Beleg, Manifest, Aufstellung). Odoo 19 erwartet 0.12.6 mit gepatchtem Qt. Unter Windows liegt die Datei meist unter `C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe`. |
| Festes GPS und Türleser | Pflicht für Position und automatischen Durchgang. Siehe die Abschnitte GPS und Scan. |
| Internet am Bürobildschirm | Pflicht für die Leaflet-Karte. Der Bus braucht nur HTTP-Zugang zum Server. |
| Postausgangsserver | Für den Verkauf nicht nötig. Nötig, damit Nachrichten Odoo wirklich verlassen. |
| CIB-, BaridiMob- oder SATIM-Gateway | Nicht enthalten. Es gibt nichts zu konfigurieren. |

Python-Pakete in der virtuellen Umgebung von Odoo:

```bash
pip install "qrcode" "Pillow"
```

Der Addon-Ordner muss `transport` heißen und in `addons_path` stehen:

```ini
[options]
addons_path = /pfad/zu/odoo/addons,/pfad/zu/custom_addons
db_host = localhost
db_port = 5432
db_user = odoo
db_password = ERSETZEN
http_port = 8069
```

Das Datenbankpasswort nicht veröffentlichen.

Installation:

```bash
python odoo-bin -c odoo.conf -d DATENBANK -i transport --stop-after-init
```

Aktualisierung nach einer Codeänderung:

```bash
python odoo-bin -c odoo.conf -d DATENBANK -u transport --stop-after-init
```

Odoo neu starten und die Datenbank öffnen. Das Menü **Transport** sieht nur ein Benutzer mit dem Privileg Transport.

Tests nur auf einer Wegwerf-Datenbank, nie auf der Fahrgastdatenbank:

```bash
python odoo-bin -c odoo.conf -d transport_ci -u transport --test-enable --test-tags /transport --stop-after-init --http-port=8071 --log-level=test
```

Das erwartete Ende ist `0 failed, 0 error(s)`.

## Benutzer

Einstellungen → Benutzer → Privileg **Transport**.

- **Dispatch**: Abfahrten, Bus, Fahrer, Buchungen, Scan, Kassenzahlung, GPS, Statistik, Aufstellung.
- **Responsable** (Leitung): alles von Dispatch, plus Linien, Haltestellen, Fahrpläne, Verträge und Kontrollpunkte.

Der Odoo-Administrator erhält **Responsable** bei der Installation. Ein interner Benutzer ohne das Privileg sieht das Menü nicht. Fahrgäste haben kein Benutzerkonto: die öffentlichen Seiten sind `auth='public'`.

## Netz, das bei der Installation geladen wird

| Code | Linie | Art | Sitzplan |
| --- | --- | --- | --- |
| ALG-MED | Algier – Médéa | Hybrid | Reisebus 2+2, Rückbank mit 5 |
| ALG-ORN | Algier – Oran | Hybrid | Vordere Tür, 2+2, Rückbank mit 5 |
| ALG-CON | Algier – Constantine | Überland | Begleitersitz, dann 2+2 |
| ALG-TIZ | Zubringer Algier – Tizi Ouzou | Firma | Minibus 2+1, Bank mit 4. Auf der öffentlichen Seite verborgen. |
| ORN-TLM | Oran – Tlemcen | Hybrid | Reisebus 2+2, Rückbank mit 5 |
| CON-ANN | Constantine – Annaba | Überland | Reisebus 2+2 bis hinten |
| ALG-BEJ | Algier – Béjaïa | Hybrid | Midibus 2+2, Kofferraum hinten |

Die Betriebsbeispiele (Verträge, Abfahrten, Fahrscheine) laufen einmal, markiert durch `transport.algeria_ops_ready`. Ein späteres `-u transport` wiederholt sie nicht. Sequenzen und E-Mail-Vorlagen sind `noupdate="1"`: eine Änderung im XML aktualisiert eine schon installierte Datenbank nicht.

Dieses Netz kann ungenutzt bleiben. Eine Linie verkauft erst, wenn der nächste Abschnitt vollständig ist. Ein fehlender Tarif stoppt den Verkauf mit « Ce trajet n'a pas de prix. »

## Minimale Einrichtung einer Linie, die verkauft

1. **Haltestellen**, jede mit einem eindeutigen Code.
2. **Linie**: Code, Art, Kapazität, Sitzanordnung, Durchschnittsgeschwindigkeit (Standard 70 km/h).
3. **Haltestellen der Linie**, in Reihenfolge. Die Distanz ist die Kilometerzahl **seit der vorherigen Haltestelle**. Die Durchfahrtszeit ist diese Distanz geteilt durch die Geschwindigkeit. Eine Verspätung verschiebt jede Haltestelle um dieselbe Minutenzahl.
4. **Ein Tarif je Paar Einstieg / Ausstieg**, im Reiter Tarife. « Preis von Ende zu Ende » ist nur ein Hinweis. Die öffentliche Seite benutzt ihn nicht.
5. **Fahrplan**: Wochentage und Uhrzeit.
6. **Betrieb → Abfahrten erzeugen**, für einen Datumsbereich.
7. **Fuhrpark → Fahrzeuge**: ein Bus mit Sitzzahl und Anordnung. Die Anordnung des Busses ersetzt die der Linie, wenn sie genau die Kapazität der Abfahrt abdeckt. Sonst bleibt die Anordnung der Linie, danach `coach_2_2`.
8. **Mitarbeiter**: der Fahrer ist ein `hr.employee` derselben Gesellschaft. **Konfiguration → Itinéraires chauffeurs** gibt ihm genau eine Linie.
9. **Konfiguration → Berechtigungen**: drei Dokumente je Fahrer, eines von jeder Art — Führerschein, ärztliche Untersuchung, Schulung — mit einem Ablaufdatum **am oder nach dem Betriebstag**. Zuweisen wird abgelehnt, solange eines fehlt.
10. **Konfiguration → Kontrollpunkte**: vier kritische Punkte werden mitgeliefert (Reifen, Öl, Licht, Bremsen). Weitere sind möglich. Beim Öffnen des Einsteigens kopiert die Abfahrt jeden aktiven Punkt.

Nützliche Linieneinstellungen:

- **Firmenreserve** und **Freigabe (Stunden vor der Abfahrt)**. Bis zu dieser Uhrzeit sind freie Einzelsitze `Kapazität − belegt − max(0, Reserve − bereits gebuchte Firmensitze)`. Danach gehen unverkaufte Firmensitze an Einzelkunden. Ein `b2b`-Zubringer erscheint nicht auf der öffentlichen Seite.
- **Stornierung (Stunden vor der Abfahrt)** und **Erstattung (%)**. Der Fahrgast storniert selbst nur vor dieser Grenze und nur für den erstatteten Anteil. Der Schalter kann später stornieren, ohne Erstattung. Das Schließen eines Betriebstags erstattet 100 % der bezahlten Fahrscheine dieses Tages, auch außerhalb der Frist.

## Systemparameter

Einstellungen → Technisch → Systemparameter.

| Schlüssel | Rolle |
| --- | --- |
| `transport.hold_minutes` | Wie lange eine Schalterbuchung gehalten wird und wie lange ein Wartelistenangebot gilt. Standard: `15`. Die öffentliche Seite verlängert die Haltung bis zur realen Abfahrtszeit, Verspätung eingeschlossen. Eine später gemeldete Verspätung schiebt diese Haltung. Eine Schalterhaltung bleibt. |
| `transport.qr_secret` | HMAC-Geheimnis für QR, Zahlungslinks, Wartelistenlinks und GPS-Links. Wird beim ersten Fahrschein selbst angelegt (`secrets.token_hex(32)`). **Nicht ändern**, nachdem Fahrscheine existieren: schon gedruckte QR bestehen den Scan nicht mehr. |
| `transport.algeria_ops_ready` | Interne Markierung. Stehen lassen, wenn die schon erzeugten Beispiele bleiben sollen. |
| `web.base.url` | Die echte Serveradresse, in Produktion mit `https://`. E-Mail-Links werden daraus gebaut. |

## Leben einer Abfahrt

Status nur vorwärts:

`Geplant → Zugewiesen → Einsteigen → Unterwegs → Beendet`

`Storniert` ist nur aus Geplant, Zugewiesen oder Einsteigen möglich, und nur wenn kein bestätigter Fahrschein und kein eingestiegener Fahrgast übrig ist. Offene Haltungen und die Warteliste werden mit der Abfahrt storniert.

- **Zuweisen**: Bus + Fahrer + drei am Betriebstag gültige Berechtigungen. Die Kapazität der Abfahrt darf die Sitzzahl des Busses nicht übersteigen.
- **Automatisch zuweisen**: wählt Bus und Fahrer nach dem nächsten Abschnitt. Nur aus Geplant.
- **Einsteigen öffnen**: erzeugt die Checkliste.
- **Starten**: jeder kritische Kontrollpunkt (die vier mitgelieferten, eigene, und ein Punkt der nach dem Öffnen des Einsteigens hinzukam) muss in Ordnung sein. Sonst bleibt der Bus stehen.
- **Beenden**: nur aus Unterwegs.
- Unterwegs, beendet oder storniert: Bus, Fahrer, Kapazität, Reserve, Uhrzeit und Freigabe sind eingefroren.
- Kraftstoff, Maut und Fahrerkosten bleiben nach Beendet eingebbar. Bei Storniert sind sie gesperrt.
- Eine Verspätung von 0 bis 720 Minuten ist möglich, bis die Abfahrt beendet oder storniert ist. Fahrgäste mit E-Mail bekommen die Vorlage « Verspätung » oder « Fahrplan wiederhergestellt », in die Warteschlange gelegt.
- **Bus tauschen**: nur Zugewiesen oder Einsteigen. Eine schon verkaufte Sitznummer über der Sitzzahl des Ersatzbusses wird abgelehnt.

Ordner unter **Betrieb → Abfahrten**:

- **Heute**: `service_date` ist der heutige Tag des Benutzers. Das ist auch das übergeordnete Menü Abfahrten.
- **Kommend**: Betriebstag strikt nach heute.
- **Archiv**: Betriebstag strikt vor heute.

`service_date` ist der lokale Tag der realen Abfahrt, Verspätung eingeschlossen. Eine Abfahrt um 23:40 mit 40 Minuten Verspätung rutscht auf den nächsten Tag. Zeitzone: die des Benutzers, sonst die des Gesellschaftskontakts, sonst `Africa/Algiers`. Ein Fahrplan wird in derselben Reihenfolge gelesen.

## Automatische Zuweisung

**Affecter automatiquement** an einer geplanten Abfahrt, dieselbe Schaltfläche auf einer Auswahl, oder **Affecter les départs à venir** an der Linie, wählt Bus und Fahrer. **Zuweisen** bleibt die manuelle Wahl.

Die Länge ist die Summe der Kilometer der Linie. **Longueur imposée** ersetzt diese Rechnung.

| Länge | Distanz | Bus |
| --- | --- | --- |
| Kurz | unter 160 km | Klein: 25 Sitze oder weniger |
| Mittel | von 160 km bis unter 300 km | Mittel: 26 bis 44 Sitze |
| Lang | 300 km und mehr | Groß: 45 Sitze und mehr |

Der gewählte Bus hat mindestens die Kapazität der Abfahrt, und sein Zeitfenster überlappt keine andere nicht stornierte Abfahrt. Die Fahrtdauer ist Distanz geteilt durch die Durchschnittsgeschwindigkeit.

Jeder Fahrer hat eine Linie: Reiter **Chauffeurs** der Linie, oder **Konfiguration → Itinéraires chauffeurs**. Hat er denselben Fahrplan gestern gefahren und ein Kollege der Linie ist frei, nimmt der Kollege die Abfahrt. Ein Fahrer fährt nicht mehr als 8 Stunden am selben Tag und kann nicht auf zwei Bussen zugleich sein. Die drei Berechtigungen müssen den Betriebstag abdecken. Eine Fahrt länger als 8 Stunden wird nicht zugewiesen.

Das Beispiel legt vier Linien fest: Karim Boudiaf auf Algier – Oran, Amina Cherif auf Algier – Constantine, Yacine Meziane auf Oran – Tlemcen, Sarah Belkacem auf den Zubringer Algier – Tizi Ouzou. Eine kurze Linie, die mehr Sitze verkauft als ein kleiner Bus hat, bekommt keine automatische Zuweisung, solange **Longueur imposée** leer ist.

## Öffentliche Seiten

Das Website-Modul ist nicht nötig. Das sind HTTP-Controller.

| Pfad | Gebrauch |
| --- | --- |
| `/reserver-un-billet` | Linie, Tag, Einstieg, Ausstieg, Sitzplan. |
| `/reserver-un-billet/envoyer` | POST. Erzeugt die Haltung und öffnet die Zahlung. |
| `/reserver-un-billet/paiement/<id>/<token>` | Zahlung und Beleg. Der Token hat 24 Hex-Zeichen. |
| `/reserver-un-billet/annuler/<id>/<token>` | POST. Stornierung durch den Fahrgast, innerhalb der Frist der Linie. |
| `/reserver-un-billet/retrouver` | Referenz (`RES/2026/0001`) + Telefon. |
| `/reserver-un-billet/attente` | POST. Warteliste, nur wenn die Fahrt 0 freie Plätze zeigt. |
| `/reserver-un-billet/attente/<id>/<token>` | Den angebotenen Platz nehmen, dann zahlen. |
| `/suivi-bus/<id>/<token>` | Karte des letzten vom Bus-GPS empfangenen Punktes. Nur Lesen. |

**Mehrere Datenbanken auf einem Odoo.** Wenn `odoo.conf` kein `db_name` hat und `dbfilter` mehr als eine Datenbank durchlässt, braucht jede öffentliche URL `?db=DATENBANK`. Die Schaltfläche **Suivi GPS** hängt `?db=` schon an. Das Menü **Réserver un billet** zeigt auf `/reserver-un-billet` ohne Datenbanknamen: in diesem Fall `?db=` selbst anfügen. Bei einer einzigen Datenbank ist der Parameter unnötig.

Die öffentliche Seite:

- verbirgt Firmenzubringer;
- lehnt eine Abfahrt ab, deren reale Uhrzeit einschließlich Verspätung erreicht ist, sowie eine stornierte, unterwegs befindliche oder beendete Abfahrt;
- verlangt einen Namen mit mindestens 2 Zeichen und ein Telefon mit mindestens 6 Zeichen;
- verkauft 1 bis 8 Plätze;
- verlangt einen Tarif für dieses Haltestellenpaar;
- zeichnet diesen Bus (oder die Linie): belegte Sitze grau, gewählte Sitze petrol, Tür und Kofferraum sind keine Sitze, Fahrer links;
- verlangt bei mehreren Plätzen einen Namen je Sitz. Ein leerer Zusatzname wird zu « Passager N »;
- zeigt die Durchfahrtszeit jeder Haltestelle.

Die Telefonsuche ignoriert Leerzeichen, `+213` und führende Nullen: `+213555123456` und `0555123456` sind derselbe Schlüssel.

## Zahlung

Die Zahlungsseite **bestätigt den Fahrschein in Odoo und lädt den Beleg herunter**. Sie ruft keine Bank auf. Keine Kartennummer und keine CVV abfragen. Es gibt keinen Händlerschlüssel.

- Online: Referenz `PAY-<Buchungs-id>`, Art `online`.
- Kasse bar: Schaltfläche **Encaisser**, Referenz `ESP-<id>`.
- Kasse Kartenterminal: Schaltfläche **Encaisser**, Referenz `TPE-<id>`.
- Ein schon bezahlter Fahrschein wechselt die Art nicht.
- Ein Firmenabonnent wird ohne Kassierung bestätigt.

Beleg, Fahrschein und Manifest sind QWeb-PDFs. Das CSS erzwingt **Arial** (`transport.report_font`), weil die Odoo-Schrift Lato mit wkhtmltopdf unter Windows schlecht druckt. Ein schon heruntergeladenes PDF behält die alte Schrift: neu erzeugen.

Ohne wkhtmltopdf liefert Odoo oft HTML statt PDF. Der Fahrgast soll eine PDF-Datei bekommen.

## Bedingungen für das GPS und den Leser, die im Bus fest sind

Jede Bedingung unten ist Pflicht. Fehlt eine, sendet der Bus nichts, oder Odoo lehnt den Punkt und den Durchgang ab.

1. **Das GPS ruft eine HTTP-Adresse auf.** Das Gerät muss die von der Bus-Karte kopierte Adresse per GET oder POST aufrufen und Breite sowie Länge anhängen. Erlaubt sind `lat` oder `latitude`, und `lon`, `lng` oder `longitude`. Ein GPS, das nur ein Binärprotokoll spricht (Teltonika-Rahmen, GT06, nur SMS), erreicht Odoo erst, wenn ein Zwischengerät diesen Aufruf übersetzt.
2. **Der Türleser ruft eine HTTP-Adresse auf.** Er muss den aus dem QR gelesenen Text senden, nicht nur das Bild. Der Text steht in `payload`, `code`, `qr` oder `data`. Ein Leser, der den QR nur auf einem Schirm zeigt, ohne HTTP-Anfrage, lässt niemanden einsteigen.
3. **Odoo öffnet das Tor nicht.** Die Software antwortet. Das Lesegerät öffnet den Durchgang nur, wenn der HTTP-Status **200** ist. Jeder andere Status (`404`, `409`) lässt den Durchgang geschlossen. Diese Schaltung sitzt im Leser, nicht in Odoo.
4. **Jeder Bus hat seinen Token.** Unter Fuhrpark → Fahrzeuge enthält **Jeton du boîtier** 32 Hex-Zeichen, erzeugt beim Speichern des Busses. Die GPS-Adresse und die Leser-Adresse enthalten diesen Token. Zwei Busse teilen ihn nie.
5. **Der Token ist das einzige Passwort.** Es gibt kein Login. Wer die Adresse hat, kann eine Position oder einen Scan senden. Nicht auf die Verkaufsseite setzen und nicht in ein öffentliches PDF.
6. **`web.base.url` ist die Adresse, die der Bus erreicht.** Einstellungen → Technisch → Systemparameter, Schlüssel `web.base.url`. In Produktion beginnt sie mit `https://` und ist der öffentliche Name des Servers. Beide auf der Bus-Karte gezeigten Adressen werden daraus gebaut. Steht dort `http://localhost:8019`, gelten sie nur auf dem Serverrechner. Ein Bus auf der Strecke löst `localhost` nicht auf.
7. **Der Datenbankname gehört zur Adresse.** Die volle Form ist `https://server/bus/<Token>/position?db=<Datenbank>` und `https://server/bus/<Token>/scan?db=<Datenbank>`. Das `?db=` ist Pflicht, solange `odoo.conf` kein einzelnes `db_name` hat. Die auf der Karte gezeigte Adresse kopieren, nicht aus dem Gedächtnis neu tippen.
8. **Jeder Bus hat einen Netzweg zu diesem Server.** Eine SIM-Karte oder ein 4G-Router im Wagen. Odoo ruft das GPS und den Leser nie an. Es wartet auf ihre Anfrage. Fällt das Netz im Moment des Punktes aus, muss das Gerät später noch einmal senden. Ein nicht gesendeter Punkt existiert nicht.
9. **Der Scan braucht eine offene Abfahrt. Das GPS nicht.** Der Leser lässt nur einsteigen, wenn dieser Bus einer Abfahrt im Status **Einsteigen** oder **Unterwegs** zugewiesen ist. Gibt es beide, empfängt die Abfahrt **Unterwegs** den Scan. Sonst antwortet der Leser mit `409`: « Ce bus n'a pas de départ en embarquement ou en course. » Das GPS speichert den Punkt immer auf der Bus-Karte. Gibt es eine offene Abfahrt, wird derselbe Punkt auch dorthin kopiert.
10. **Der QR ist der von Odoo gedruckte.** Der genaue Text ist `TRP:<Buchungs-id>:<20 Hex-Zeichen>`. Die Signatur wird mit dem Parameter `transport.qr_secret` geprüft. Dieses Geheimnis nach dem Druck von Fahrscheinen nicht ändern: schon ausgegebene QR werden abgelehnt.
11. **Der Fahrschein ist bestätigt, bei einem Einzelfahrschein bezahlt, und er gehört zu dieser Abfahrt.** Ein Firmenabonnent geht ohne Kassierung durch. Ein unbezahlter Einzelfahrschein erhält `409`: « Ce billet individuel n'est pas payé. » Ein gehaltener, stornierter, schon eingestiegener oder auf eine andere Abfahrt gebuchter Fahrschein erhält ebenfalls `409`, und das Tor bleibt zu. Ein zweiter Durchgang desselben QR wird abgelehnt, weil der Fahrschein nicht mehr « bestätigt » ist.
12. **Die Karte der Verwaltung braucht Internet am Bürobildschirm.** Die Schaltfläche **Suivi GPS** lädt Leaflet und die OpenStreetMap-Kacheln. Das ist unabhängig vom Netz des Busses. Ohne diese Kacheln ist der Punkt trotzdem gespeichert, die Karte bleibt leer.

## Fahrschein-Scan

Der fest an der Bustür montierte Leser sendet den QR-Text an Odoo. Der Fahrer hält kein Telefon. Odoo steuert den Torantrieb nicht: das Lesegerät muss den Durchgang öffnen, wenn der HTTP-Status **200** ist, und ihn bei jedem anderen Status geschlossen halten.

1. Auf der Bus-Karte (Fuhrpark → Fahrzeuge) **Adresse du lecteur** kopieren. Sie hat die Form `https://server/bus/<32 Hex-Token>/scan?db=<Datenbank>`.
2. Diese Adresse im Leser eintragen. Der QR-Text geht in `payload`, `code`, `qr` oder `data`, per GET oder POST. Der Token nennt den Bus. Kein Login.
3. Der Bus braucht eine Abfahrt im Status **Einsteigen** oder **Unterwegs**, mit diesem Fahrzeug. Eine Abfahrt unterwegs hat Vorrang. Sonst empfängt die Abfahrt im Einsteigen den Scan.
4. Der gedruckte QR ist genau `TRP:<Buchungs-id>:<20 Hex-Zeichen>`. Odoo prüft die Signatur mit `transport.qr_secret`.
5. Status `200` und der Name: der Fahrschein wird Eingestiegen. Das Gerät kann das Tor öffnen und den Namen zeigen.
6. Status `409`: der Fehlertext (Fahrschein abgelehnt, andere Abfahrt, storniert, nicht bestätigt, Bus ohne offene Abfahrt). Das Tor bleibt zu.
7. Status `404` und « Bus inconnu. »: der Token gehört zu keinem Bus.

Der Bus braucht einen Netzweg zum Server (4G-Router). `web.base.url` muss die Adresse sein, die der Bus erreicht, in Produktion `https://`. `localhost` gilt nur auf dem Serverrechner.

Die Schaltfläche **Scanner un billet** an der Abfahrt bleibt ohne festen Leser nutzbar: Telefonkamera oder Feld für einen Tastatur-Scanner. Das ist nicht das Tor.

Ablehnungen, mit der Meldung der Software:

- unbekannte Signatur oder veränderter Text: « Billet refusé. »
- andere Abfahrt: « Ce billet est pour un autre départ. »
- stornierter Fahrschein: « Ce billet est annulé. »
- Buchung noch nicht bestätigt: « Seul un billet confirmé s'embarque. »
- Abfahrt noch Geplant oder Zugewiesen: « L'embarquement n'est pas ouvert sur ce départ. »

Ein QR entsteht bei der Bestätigung und wird nie umgeschrieben. Ein zweiter Scan eines schon eingestiegenen Fahrgasts scheitert, weil die Buchung nicht mehr « bestätigt » ist.

Das Manifest der Abfahrt druckt eine Zeile je Sitz: Nummer, Name, Kanal, Einstieg, Ausstieg, Status.

## GPS

Das im Bus fest eingebaute GPS sendet seine Position von selbst. Der Fahrer tippt nichts.

1. Auf der Bus-Karte **Adresse GPS** kopieren. Sie hat die Form `https://server/bus/<32 Hex-Token>/position?db=<Datenbank>`.
2. Diese Adresse im Gerät eintragen und Breite sowie Länge anhängen. Erlaubt sind `lat` oder `latitude`, und `lon`, `lng` oder `longitude`. Beispiel: die Adresse gefolgt von `&lat=36.7538&lon=3.0588`. GET, Formular-POST oder JSON gehen.
3. Der Punkt wird immer auf der Bus-Karte gespeichert. Gibt es eine Abfahrt **Unterwegs**, sonst **Einsteigen**, wird derselbe Punkt dorthin kopiert. Beide Karten zeigen die letzte Breite, die letzte Länge und die Uhrzeit.
4. Status `200` und `ok`: der Punkt ist gespeichert, auch ohne offene Abfahrt. `409`: Koordinaten unlesbar oder außerhalb (−90..90, −180..180). `404`: unbekannter Token.
5. Dieselbe 4G-Verbindung wie der Türleser genügt. Ist das Netz in dem Moment weg, muss das Gerät den Punkt später noch einmal senden. Odoo ruft das GPS nicht an. Es wartet auf den Anruf.
6. Die Schaltfläche **Suivi GPS** an der Abfahrt öffnet nur die Karte des schon empfangenen Punktes (Leaflet und OpenStreetMap, der Bildschirm der Verwaltung braucht also Internet). Von dieser Seite sendet niemand eine Position.

Der Bus-Token ist geheim. Wer ihn hat, kann eine falsche Position oder einen Scan senden. Nicht auf die Verkaufsseite setzen.

## Warteliste

Die öffentliche Schaltfläche erscheint nur, wenn die Fahrt 0 freie Plätze zeigt. Die Anmeldung erzeugt `ATT/Jahr/....`.

Ein aktives Angebot je Abfahrt. Es geht an die erste wartende Person, deren Platzzahl in die freien Einzelsitze passt (die Firmenreserve bleibt geschützt). Das Angebot dauert `transport.hold_minutes`. Der Cron **Transport : libérer les réservations expirées** läuft alle 5 Minuten: er storniert abgelaufene Haltungen, lässt verspätete Angebote verfallen und bietet dann der nächsten Person an. Odoo muss laufen, damit der Cron startet.

Das Annehmen erzeugt eine gehaltene Buchung. Der Platz ist erst nach der Zahlung bestätigt.

## E-Mail

Vorlagen, alle in die Warteschlange (`force_send=False`):

- ausgestellter Fahrschein, wenn eine Adresse da ist;
- Verspätung und wiederhergestellter Fahrplan;
- umgebuchter Fahrschein;
- Wartelistenangebot;
- Schließen eines Betriebstags.

Ohne Postausgangsserver (Einstellungen → Technisch → Postausgangsserver) und ohne den Mail-Cron bleibt die Nachricht in Odoo. `web.base.url` vor dem Senden setzen, sonst zeigen die Links auf `localhost`.

## Ergebnis, Statistik, Aufstellung

- Reiter **Ergebnis** der Abfahrt: verkaufte Plätze (bestätigt, eingestiegen, No-show), eingenommen, erstattet, Auslastung je Teilstrecke, Kraftstoff, Maut, Fahrer, Marge. Die Marge ist eingenommen − erstattet − Kosten.
- **Betrieb → Statistik**: für einen Zeitraum, je Linie, verkaufte Plätze, angebotene Plätze, Auslastung, Warteliste, Marge, Hauptstrecke. Der Gewinn des Zeitraums ist die Summe der Margen der nicht stornierten Abfahrten.
- Die Vorschläge lesen diese Zahlen. Sie rufen kein externes Modell auf. Auslastung ≥ 75 % oder mindestens 2 Wartende: eine weitere Abfahrt auf der meistverkauften Strecke vorschlagen. Auslastung ≤ 40 % und ein Bus im Fuhrpark, der die verkaufte Spitze mit weniger Sitzen als die Linie abdeckt: diesen Bus vorschlagen. Ein Vorschlag erfindet keine nie verkaufte Linie.
- **Unternehmen → Monatsaufstellung**, oder die Schaltfläche **Relevé** am Vertrag: PDF der Abonnentfahrten im Status bestätigt, eingestiegen oder No-show im Zeitraum. Die Fußzeile sagt, dass es keine Rechnung ist.

## Einen Betriebstag schließen

**Betrieb → Fermer une journée**, oder die Schaltfläche an der Linie. Ein Grund ist Pflicht. Eine leere Linie bedeutet alle Linien.

Der gewählte Tag storniert Abfahrten in Geplant, Zugewiesen und Einsteigen. Bezahlte Fahrscheine dieser Abfahrten werden vollständig erstattet. Ihre Warteliste wird storniert. Eine Abfahrt **Unterwegs** bleibt. Eine Abfahrt, die schon einen eingestiegenen Fahrgast hat, bleibt. Andere Tage bleiben unverändert.

## Sequenzen

| Dokument | Form |
| --- | --- |
| Abfahrt | `DEP/2026/0001` |
| Buchung | `RES/2026/0001` |
| Vertrag | `CTR/2026/0001` |
| Warteliste | `ATT/2026/0001` |

## Kurze Fehlersuche

| Symptom | Häufige Ursache |
| --- | --- |
| Kein Menü Transport | Der Benutzer hat weder Dispatch noch Responsable. |
| « Ce trajet n'a pas de prix. » | Kein Tarif für dieses Paar Einstieg / Ausstieg. |
| Zuweisen abgelehnt | Bus, Fahrer oder eine der drei Berechtigungen fehlt oder läuft vor dem Betriebstag ab. |
| Automatische Zuweisung abgelehnt | Keine Distanz auf der Linie, kein Fahrer auf dieser Linie, kein freier Bus der richtigen Größe mit genug Sitzen, Fahrer schon unterwegs, oder mehr als 8 Fahrstunden an diesem Tag. |
| Starten abgelehnt | Ein kritischer Kontrollpunkt ist nicht in Ordnung. |
| QR geht nicht | Text unvollständig, falsche Abfahrt, Fahrschein nicht bestätigt, oder `transport.qr_secret` wurde geändert. |
| Die Kamera öffnet sich nicht | Die Seite wurde von einem anderen Gerät über HTTP geöffnet, oder die Freigabe wurde verweigert. Das QR-Feld bleibt benutzbar. HTTPS verwenden. |
| Der GPS-Kasten sendet nichts | Die am Bus kopierte Adresse ist nicht erreichbar, das Token ist falsch, oder die Parameter heißen nicht `lat`/`lon`. |
| Leere Karte | Kein Internet zu unpkg oder OpenStreetMap, oder noch keine Position gesendet. |
| PDF-Buchstaben unleserlich | Altes PDF, oder wkhtmltopdf fehlt. Nach der Aktualisierung neu erzeugen. Die erzwungene Schrift ist Arial. |
| E-Mail kommt nie an | Kein Postausgangsserver, oder der Fahrgast hat keine Adresse. |
| Die öffentliche Seite fragt nach der Datenbank | `?db=DATENBANK` anfügen. |
| Die Abfahrten von gestern stehen unter Heute | Modul aktualisieren. Der Filter ist `service_date`, nicht der alte Filter « offen ». |

---

# العربية

<div dir="rtl">

## ماذا يفعل هذا التطبيق

استغلال واحد، وقناتان للبيع.

- **تذكرة فردية**: الراكب يحجز في الصفحة العامة، ويدفع في صفحة الشركة، وينزّل إيصالاً بصيغة PDF وتذكرة فيها رمز QR.
- **مشترك شركة**: الشباك يؤكد المقعد على عقد. المشترك لا يدفع في الشباك. الكشف الشهري يسرد الرحلات. هذا الكشف ليس فاتورة محاسبية.

المقعد يُحسب على كل مقطع. راكب الجزائر → البليدة يشغل المقاطع حتى البليدة. بعد البليدة يمكن بيع رقم المقعد نفسه من جديد.

المبالغ المحصّلة، والمبالغ المستردة، والوقود، والطريق السيار، وأجرة السائق، والهامش تبقى على الرحلة. التطبيق لا ينشئ قيداً محاسبياً `account.move`. وهو لا يعتمد على المحاسبة، ولا على المبيعات، ولا على موقع الويب، ولا على الدفع.

## ما يجب تثبيته بالضبط

| العنصر | الشرط |
| --- | --- |
| أودو | 19.0. التطبيق يستعمل `models.Constraint` وعروض `<list>` و`<chatter/>`. |
| بايثون | 3.10 أو أحدث. هذه البيئة تستعمل 3.13. |
| PostgreSQL | قاعدة مستقلة. مستخدم القاعدة يجب أن يستطيع إنشاء الجداول. |
| تطبيقات أودو | `base` و`mail` و`fleet` و`hr`. أودو يثبّتها مع Transport. |
| حزمة بايثون `qrcode` | إلزامية. رمز QR على التذكرة صورة PNG. من دون هذه الحزمة يتوقف إصدار التذكرة. |
| حزمة بايثون `Pillow` | إلزامية. `qrcode` يحفظ PNG عبر Pillow. ReportLab لا يُستعمل لرمز QR. |
| wkhtmltopdf | إلزامي للحصول على PDF حقيقي (التذكرة، الإيصال، كشف الركاب، الكشف الشهري). أودو 19 ينتظر الإصدار 0.12.6 مع Qt المصحح. في ويندوز يكون الملف عادة `C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe`. |
| جهاز GPS ثابت وقارئ الباب | إلزاميان للموضع وللمرور الآلي. انظر قسمي GPS والمسح. |
| الإنترنت على شاشة المكتب | إلزامي لخريطة Leaflet. الحافلة تحتاج فقط وصول HTTP إلى الخادم. |
| خادم بريد صادر | اختياري للبيع. إلزامي إذا كانت الرسائل يجب أن تغادر أودو فعلاً. |
| بوابة CIB أو BaridiMob أو SATIM | غير موجودة. لا تبحث عن مفتاح تاجر في التطبيق. |

تثبيت حزم بايثون داخل البيئة الافتراضية لأودو:

```bash
pip install "qrcode" "Pillow"
```

مجلد التطبيق يجب أن يبقى اسمه `transport` وأن يكون داخل مسار `addons_path`:

```ini
[options]
addons_path = /path/to/odoo/addons,/path/to/custom_addons
db_host = localhost
db_port = 5432
db_user = odoo
db_password = REPLACE
http_port = 8069
```

لا تضع كلمة سر القاعدة في ملف عام.

التثبيت:

```bash
python odoo-bin -c odoo.conf -d DATABASE -i transport --stop-after-init
```

التحديث بعد تغيير في الكود:

```bash
python odoo-bin -c odoo.conf -d DATABASE -u transport --stop-after-init
```

أعد تشغيل أودو وافتح القاعدة. قائمة **Transport** تظهر للمستخدم الذي يملك صلاحية Transport.

الاختبارات على قاعدة مؤقتة، لا على قاعدة الركاب:

```bash
python odoo-bin -c odoo.conf -d transport_ci -u transport --test-enable --test-tags /transport --stop-after-init --http-port=8071 --log-level=test
```

النهاية المتوقعة هي `0 failed, 0 error(s)`.

## المستخدمون

الإعدادات → المستخدمون → صلاحية **Transport**.

- **Dispatch**: الرحلات، الحافلة، السائق، الحجوزات، المسح، التحصيل، GPS، الإحصاء، الكشف.
- **Responsable**: كل ما في Dispatch، إضافة إلى الخطوط، والمحطات، والجداول، والعقود، ونقاط المراقبة.

مدير أودو يحصل على **Responsable** عند التثبيت. المستخدم الداخلي من دون هذه الصلاحية لا يرى القائمة. الراكب ليس له حساب: الصفحات العامة بـ `auth='public'`.

## الشبكة التي تُحمَّل عند التثبيت

| الرمز | الخط | النوع | ترتيب المقاعد |
| --- | --- | --- | --- |
| ALG-MED | الجزائر – المدية | مختلط | حافلة 2+2، مقعد خلفي لخمسة |
| ALG-ORN | الجزائر – وهران | مختلط | باب أمامي، 2+2، مقعد خلفي لخمسة |
| ALG-CON | الجزائر – قسنطينة | بين المدن | مقعد المرافق، ثم 2+2 |
| ALG-TIZ | نقل الجزائر – تيزي وزو | شركة | حافلة صغيرة 2+1، مقعد لأربعة. مخفية في الصفحة العامة. |
| ORN-TLM | وهران – تلمسان | مختلط | حافلة 2+2، مقعد خلفي لخمسة |
| CON-ANN | قسنطينة – عنابة | بين المدن | حافلة 2+2 حتى آخر الصف |
| ALG-BEJ | الجزائر – بجاية | مختلط | حافلة متوسطة 2+2، صندوق خلفي |

بيانات الاستغلال التجريبية (عقود، رحلات، تذاكر) تُنشأ مرة واحدة، وتُعلَّم بـ `transport.algeria_ops_ready`. تشغيل `-u transport` لاحقاً لا يعيدها. الترقيمات وقوالب البريد `noupdate="1"`: تعديل XML لا يحدّث قاعدة مثبتة من قبل.

يمكن تجاهل هذه الشبكة وبناء شبكة أخرى. الخط لا يُباع إلا إذا اكتملت الفقرة التالية. تعرفة ناقصة توقف البيع برسالة « Ce trajet n'a pas de prix. »

## الحد الأدنى لخط يبيع

1. **المحطات**، لكل واحدة رمز فريد.
2. **الخط**: الرمز، النوع، السعة، ترتيب المقاعد، السرعة المتوسطة (70 كم/س افتراضياً).
3. **محطات الخط** بالترتيب. المسافة هي الكيلومترات **منذ المحطة السابقة**. وقت المرور هو هذه المسافة مقسومة على السرعة. التأخر يزيح كل المحطات بعدد الدقائق نفسه.
4. **تعرفة لكل زوج صعود / نزول** في تبويب التعرفات. « سعر الطرف إلى الطرف » إرشادي فقط. الصفحة العامة لا تستعمله.
5. **الجدول**: أيام الأسبوع والساعة.
6. **الاستغلال → توليد الرحلات**، على مدى تواريخ.
7. **الأسطول → المركبات**: حافلة بعدد مقاعد وترتيب. ترتيب الحافلة يحل محل ترتيب الخط عندما يطابق سعة الرحلة تماماً. وإلا تبقى الرحلة على ترتيب الخط، ثم `coach_2_2`.
8. **الموظفون**: السائق سجل `hr.employee` في الشركة نفسها. **الإعداد → Itinéraires chauffeurs** يعطيه خطاً واحداً.
9. **الإعداد → التأهيلات**: ثلاث وثائق لكل سائق، واحدة من كل نوع — رخصة السياقة، الفحص الطبي، التكوين — وتاريخ انتهاء **في يوم الرحلة أو بعده**. زر التعيين يُرفض إذا نقصت واحدة.
10. **الإعداد → نقاط المراقبة**: أربع نقاط حرجة تأتي مع التطبيق (العجلات، الزيت، الأضواء، الفرامل). يمكن إضافة غيرها. عند فتح الركوب تنسخ الرحلة كل نقطة نشطة.

إعدادات مفيدة على الخط:

- **احتياط الشركات** و**التحرير (ساعات قبل الانطلاق)**. حتى هذه الساعة، المقاعد الفردية الحرة تساوي `السعة − المحجوز − max(0, الاحتياط − مقاعد الشركات المحجوزة)`. بعدها يعود ما لم يُبع من احتياط الشركات إلى الأفراد. خط الشركات `b2b` لا يظهر في الصفحة العامة.
- **الإلغاء (ساعات قبل الانطلاق)** و**نسبة الاسترداد (%)**. الراكب يلغي بنفسه فقط قبل هذا الحد، وفقط بالنسبة المستردة. الشباك يستطيع الإلغاء بعد ذلك بلا استرداد. إغلاق يوم عمل يسترد 100٪ من التذاكر المدفوعة في ذلك اليوم، حتى خارج المهلة.

## معاملات النظام

الإعدادات → التقني → معاملات النظام.

| المفتاح | الدور |
| --- | --- |
| `transport.hold_minutes` | مدة حجز الشباك، ومدة عرض قائمة الانتظار. الافتراضي: `15`. الصفحة العامة تمدد الحجز حتى ساعة الانطلاق الحقيقية، مع التأخر. تأخر يُعلن لاحقاً يؤخر هذا الحجز. حجز الشباك لا يتحرك. |
| `transport.qr_secret` | سر HMAC لرموز QR وروابط الدفع وروابط الانتظار وروابط GPS. يُنشأ وحده عند أول تذكرة (`secrets.token_hex(32)`). **لا تغيّره** بعد إصدار التذاكر: الرموز المطبوعة لن تنجح في المسح. |
| `transport.algeria_ops_ready` | علامة داخلية. اتركها إذا أردت الإبقاء على المثال الذي أُنشئ. |
| `web.base.url` | عنوان الخادم الحقيقي، مع `https://` في الإنتاج. روابط البريد تُبنى منه. |

## حياة الرحلة

الحالات تتقدم فقط:

`مخطط → معيَّن → ركوب → في الطريق → منتهٍ`

`ملغى` ممكن فقط من مخطط أو معيَّن أو ركوب، وفقط إذا لم يبقَ تذكرة مؤكدة ولا راكب صعد. الحجوزات المعلقة وقائمة الانتظار تُلغى مع الرحلة.

- **تعيين**: حافلة + سائق + ثلاث تأهيلات صالحة في يوم الخدمة. سعة الرحلة لا تتجاوز عدد مقاعد الحافلة.
- **تعيين تلقائي**: يختار الحافلة والسائق حسب القسم التالي. فقط من حالة مخطط.
- **فتح الركوب**: ينشئ قائمة المراقبة.
- **الانطلاق**: كل نقطة حرجة (الأربع المرفقة وما أضفته، بما فيه نقطة أُضيفت بعد فتح الركوب) يجب أن تكون مطابقة. وإلا تبقى الحافلة في المحطة.
- **إنهاء**: فقط من حالة في الطريق.
- في الطريق، أو منتهٍ، أو ملغى: الحافلة والسائق والسعة والاحتياط والساعة والتحرير مجمّدة.
- الوقود والطريق السيار والسائق تبقى قابلة للإدخال بعد الإنهاء. وهي ممنوعة على الملغى.
- تأخر من 0 إلى 720 دقيقة ممكن ما دامت الرحلة ليست منتهية ولا ملغاة. الركاب الذين لهم بريد يستلمون قالب « تأخر » أو « عودة الجدول »، ويوضع في الطابور.
- **تبديل الحافلة**: فقط في معيَّن أو ركوب. رقم مقعد مبيع أعلى من مقاعد الحافلة البديلة يُرفض.

مجلدات **الاستغلال → الرحلات**:

- **اليوم**: `service_date` يساوي يوم المستخدم. وهو أيضاً قائمة الرحلات الأم.
- **القادمة**: تاريخ الخدمة بعد اليوم حصراً.
- **المؤرشفة**: تاريخ الخدمة قبل اليوم حصراً.

`service_date` هو اليوم المحلي للانطلاق الحقيقي، مع التأخر. رحلة 23:40 بتأخر 40 دقيقة تنتقل إلى اليوم التالي. المنطقة الزمنية: منطقة المستخدم، وإلا منطقة جهة اتصال الشركة، وإلا `Africa/Algiers`. جدول المواعيد يُقرأ بالترتيب نفسه.

## التعيين التلقائي

الزر **Affecter automatiquement** على رحلة مخططة، أو الزر نفسه على مجموعة رحلات، أو **Affecter les départs à venir** على الخط، يختار الحافلة والسائق. زر **تعيين** يبقى الاختيار اليدوي.

الطول هو مجموع كيلومترات الخط. **Longueur imposée** تستبدل هذا الحساب.

| الطول | المسافة | الحافلة |
| --- | --- | --- |
| قصير | أقل من 160 كم | صغيرة: 25 مقعداً أو أقل |
| متوسط | من 160 كم إلى أقل من 300 كم | متوسطة: من 26 إلى 44 مقعداً |
| طويل | 300 كم وأكثر | كبيرة: 45 مقعداً وأكثر |

الحافلة المختارة فيها على الأقل سعة الرحلة، ووقتها لا يتقاطع مع رحلة أخرى غير ملغاة. مدة الرحلة هي المسافة مقسومة على السرعة المتوسطة.

لكل سائق خط واحد: لسان **Chauffeurs** في الخط، أو **الإعداد → Itinéraires chauffeurs**. إذا قاد الجدول نفسه أمس وكان زميل على الخط حراً، يأخذ الزميل الرحلة. السائق لا يتجاوز 8 ساعات قيادة في اليوم نفسه، ولا يمكن أن يكون على حافلتين في الوقت نفسه. التأهيلات الثلاث يجب أن تغطي يوم الخدمة. رحلة أطول من 8 ساعات لا تُعيَّن.

المثال يضع أربعة خطوط: Karim Boudiaf على الجزائر – وهران، Amina Cherif على الجزائر – قسنطينة، Yacine Meziane على وهران – تلمسان، Sarah Belkacem على مكوك الجزائر – تيزي وزو. خط قصير يبيع مقاعد أكثر مما تحمله حافلة صغيرة لا يحصل على تعيين تلقائي حتى تُضبط **Longueur imposée**.

## الصفحات العامة

تطبيق موقع الويب غير مطلوب. هذه متحكمات HTTP.

| المسار | الاستعمال |
| --- | --- |
| `/reserver-un-billet` | الخط، اليوم، الصعود، النزول، مخطط المقاعد. |
| `/reserver-un-billet/envoyer` | POST. ينشئ الحجز ويفتح الدفع. |
| `/reserver-un-billet/paiement/<id>/<token>` | الدفع والإيصال. الرمز 24 حرفاً ست عشرياً. |
| `/reserver-un-billet/annuler/<id>/<token>` | POST. إلغاء الراكب، داخل مهلة الخط. |
| `/reserver-un-billet/retrouver` | المرجع (`RES/2026/0001`) + الهاتف. |
| `/reserver-un-billet/attente` | POST. قائمة الانتظار، فقط إذا أظهرت الرحلة 0 مقعد. |
| `/reserver-un-billet/attente/<id>/<token>` | أخذ المقعد المعروض، ثم الدفع. |
| `/suivi-bus/<id>/<token>` | خريطة آخر نقطة استقبلها GPS الحافلة. للقراءة فقط. |

**عدة قواعد على أودو واحد.** إذا لم يوجد `db_name` في `odoo.conf` وكان `dbfilter` يمرر أكثر من قاعدة، كل عنوان عام يحتاج `?db=DATABASE`. زر **Suivi GPS** يضيف `?db=` مسبقاً. قائمة **Réserver un billet** تشير إلى `/reserver-un-billet` بلا اسم قاعدة: أضف `?db=` بنفسك في هذه الحالة. مع قاعدة واحدة المعامل غير لازم.

الصفحة العامة:

- تخفي خطوط الشركات؛
- ترفض رحلة بلغت ساعتها الحقيقية، مع التأخر، وكذلك رحلة أُلغيت أو هي في الطريق أو انتهت؛
- تطلب اسماً من حرفين على الأقل وهاتفاً من 6 أحرف على الأقل؛
- تبيع من مقعد واحد إلى 8؛
- تطلب تعرفة لزوج المحطتين؛
- ترسم تلك الحافلة (أو الخط): المأخوذ رمادي، والمختار فيروزي، والباب والصندوق ليسا مقعدين، والسائق على اليسار؛
- إذا تعددت المقاعد تطلب اسماً لكل مقعد. الاسم الفارغ يصبح « Passager N »؛
- تعرض ساعة المرور عند كل محطة.

البحث بالهاتف يتجاهل المسافات و`+213` والأصفار في البداية: `+213555123456` و`0555123456` مفتاح واحد.

## الدفع

صفحة الدفع **تؤكد التذكرة داخل أودو وتنزّل الإيصال**. هي لا تتصل بأي بنك. لا تطلب رقم البطاقة ولا CVV. لا يوجد مفتاح تاجر.

- عبر الصفحة: المرجع `PAY-<معرّف الحجز>`، الطريقة `online`.
- الصندوق نقداً: زر **Encaisser**، المرجع `ESP-<id>`.
- الصندوق بجهاز TPE: زر **Encaisser**، المرجع `TPE-<id>`.
- تذكرة مدفوعة لا تغيّر طريقتها.
- مشترك الشركة يُؤكد بلا تحصيل.

الإيصال والتذكرة وكشف الركاب ملفات PDF من QWeb. التنسيق يفرض **Arial** (`transport.report_font`)، لأن خط Lato في أودو يُطبع بشكل سيئ مع wkhtmltopdf على ويندوز. ملف PDF نُزّل من قبل يحتفظ بالخط القديم: يجب إعادة توليده.

من دون wkhtmltopdf يعيد أودو غالباً HTML بدل PDF. الراكب يجب أن يستلم ملف PDF.

## شروط GPS والقارئ المثبتين في الحافلة

كل شرط أدناه إلزامي. إذا غاب شرط واحد، الحافلة لا ترسل شيئاً، أو أودو يرفض النقطة والمرور.

1. **جهاز GPS ينادي عنوان HTTP.** الجهاز يجب أن يرسل GET أو POST إلى العنوان المنسوخ من بطاقة الحافلة، ويضيف خط العرض وخط الطول. الأسماء المقبولة هي `lat` أو `latitude`، و`lon` أو `lng` أو `longitude`. جهاز GPS لا يتكلم إلا بروتوكولاً ثنائياً (إطار Teltonika أو GT06 أو SMS فقط) لا يبلغ أودو حتى يترجم صندوق وسيط هذا النداء.
2. **قارئ الباب ينادي عنوان HTTP.** يجب أن يرسل النص المقروء من QR، لا الصورة وحدها. النص يوضع في `payload` أو `code` أو `qr` أو `data`. قارئ يعرض QR على شاشة بلا طلب HTTP لا يُصعد الراكب.
3. **أودو لا يفتح البوابة.** البرنامج يجيب. صندوق القارئ يفتح المرور فقط عندما يكون رمز HTTP **200**. أي رمز آخر (`404` أو `409`) يُبقي المرور مغلقاً. هذا الربط يُضبط في القارئ، لا في أودو.
4. **لكل حافلة رمزها.** في الأسطول → المركبات، الحقل **Jeton du boîtier** فيه 32 حرفاً ست عشرياً، يُنشأ عند حفظ الحافلة. عنوان GPS وعنوان القارئ يحتويان هذا الرمز. حافلتان لا تشتركان فيه أبداً.
5. **الرمز هو كلمة السر الوحيدة.** لا يوجد تسجيل دخول. من يملك العنوان يستطيع إرسال موقعاً أو مسحاً. لا تضعه في صفحة البيع ولا في PDF عام.
6. **`web.base.url` هو العنوان الذي تبلغه الحافلة.** الإعدادات → التقني → معاملات النظام، المفتاح `web.base.url`. في الإنتاج يبدأ بـ `https://` وهو الاسم العام للخادم. العنوانان الظاهران على بطاقة الحافلة يُبنيان من هذه القيمة. إذا كانت `http://localhost:8019` فهما يعملان فقط على حاسوب الخادم. حافلة على الطريق لا تجد `localhost`.
7. **اسم القاعدة جزء من العنوان.** الشكل الكامل هو `https://الخادم/bus/<الرمز>/position?db=<القاعدة>` و`https://الخادم/bus/<الرمز>/scan?db=<القاعدة>`. `?db=` إلزامي ما دام `odoo.conf` بلا `db_name` واحد. انسخ العنوان الظاهر على البطاقة، لا تعد كتابته من الذاكرة.
8. **لكل حافلة شبكة نحو هذا الخادم.** شريحة SIM أو موجه 4G داخل الحافلة. أودو لا ينادي GPS ولا القارئ أبداً. هو ينتظر طلبهما. إذا سقطت الشبكة لحظة النقطة، يجب أن يعيد الجهاز الإرسال لاحقاً. نقطة لم تُرسل لا وجود لها.
9. **المسح يحتاج رحلة مفتوحة. GPS لا يحتاج.** القارئ لا يُصعد راكباً إلا إذا كانت هذه الحافلة معيَّنة على رحلة في **ركوب** أو **في الطريق**. إذا وُجد الاثنان، رحلة **في الطريق** تستقبل المسح. وإلا يجيب القارئ `409`: « Ce bus n'a pas de départ en embarquement ou en course. » GPS يسجّل النقطة دائماً على بطاقة الحافلة. إذا وُجدت رحلة مفتوحة، تُنسخ النقطة نفسها إلى تلك الرحلة.
10. **رمز QR هو الذي طبعه أودو.** النص بالضبط `TRP:<معرّف الحجز>:<20 حرفاً ست عشرياً>`. التوقيع يُفحص بمعامل `transport.qr_secret`. لا تغيّر هذا السر بعد طبع التذاكر: رموز QR التي خرجت تُرفض.
11. **التذكرة مؤكدة، ومدفوعة إذا كانت فردية، وهي لهذه الرحلة.** مشترك الشركة يمر بلا تحصيل. التذكرة الفردية غير المدفوعة تأخذ `409`: « Ce billet individuel n'est pas payé. » تذكرة معلقة، أو ملغاة، أو ركب صاحبها، أو محجوزة على رحلة أخرى، تأخذ أيضاً `409`، والبوابة تبقى مغلقة. مرور ثانٍ لرمز QR نفسه يُرفض، لأن التذكرة لم تعد « مؤكدة ».
12. **خريطة الإدارة تحتاج إلى الإنترنت على شاشة المكتب.** زر **Suivi GPS** يحمّل Leaflet وبلاطات OpenStreetMap. هذا منفصل عن شبكة الحافلة. بلا هذه البلاطات تبقى النقطة مسجّلة، والخريطة فارغة.

## مسح التذاكر

القارئ المثبت أمام باب الحافلة يرسل نص QR إلى أودو. السائق لا يمسك هاتفاً. أودو لا يحرّك محرك البوابة: صندوق القارئ يجب أن يفتح المرور عندما يكون جواب HTTP **200**، وأن يبقيه مغلقاً لأي رمز آخر.

1. في بطاقة الحافلة (الأسطول → المركبات) انسخ **Adresse du lecteur**. شكلها `https://الخادم/bus/<رمز من 32 ست عشري>/scan?db=<القاعدة>`.
2. اضبط القارئ على هذا العنوان. نص QR يُرسل في `payload` أو `code` أو `qr` أو `data`، بـ GET أو POST. الرمز يعرّف الحافلة. لا حاجة إلى تسجيل دخول.
3. يجب أن تكون للحافلة رحلة في **ركوب** أو **في الطريق** وهذه المركبة معيَّنة عليها. رحلة في الطريق لها الأولوية. وإلا فالاستقبال يكون لرحلة الركوب.
4. رمز QR المطبوع هو بالضبط `TRP:<معرّف الحجز>:<20 حرفاً ست عشرياً>`. أودو يتحقق من التوقيع بمفتاح `transport.qr_secret`.
5. الجواب `200` واسم الراكب: التذكرة تصبح ركب. الصندوق يستطيع فتح البوابة وإظهار الاسم.
6. الجواب `409`: نص الخطأ (تذكرة مرفوضة، رحلة أخرى، ملغاة، غير مؤكدة، حافلة بلا رحلة مفتوحة). البوابة تبقى مغلقة.
7. الجواب `404` و« Bus inconnu. »: الرمز ليس رمز حافلة.

الحافلة تحتاج إلى شبكة حتى الخادم (موجه 4G). `web.base.url` يجب أن يكون العنوان الذي تبلغه الحافلة، وبـ `https://` في الإنتاج. `localhost` يعمل فقط على جهاز الخادم.

زر **Scanner un billet** على الرحلة يبقى صالحاً بلا قارئ ثابت: كاميرا هاتف، أو حقل لماسح لوحة مفاتيح. هذا ليس البوابة.

حالات الرفض، برسالة البرنامج نفسها:

- توقيع مجهول أو نص معدّل: « Billet refusé. »
- رحلة أخرى: « Ce billet est pour un autre départ. »
- تذكرة ملغاة: « Ce billet est annulé. »
- الحجز لم يُؤكد بعد: « Seul un billet confirmé s'embarque. »
- الرحلة ما زالت مخططاً أو معيَّنة: « L'embarquement n'est pas ouvert sur ce départ. »

رمز QR يُنشأ عند التأكيد ولا يُعاد كتابته. مسح ثانٍ لراكب ركب من قبل يفشل، لأن الحجز لم يعد « مؤكداً ».

كشف الركاب يطبع سطراً لكل مقعد: الرقم، الاسم، القناة، الصعود، النزول، الحالة.

## GPS

جهاز GPS المثبت في الحافلة يرسل موقعه وحده. السائق لا يضغط شيئاً.

1. في بطاقة الحافلة انسخ **Adresse GPS**. شكلها `https://الخادم/bus/<رمز من 32 ست عشري>/position?db=<القاعدة>`.
2. ضع هذا العنوان في الجهاز واجعله يضيف خط العرض وخط الطول. الأسماء المقبولة هي `lat` أو `latitude`، و`lon` أو `lng` أو `longitude`. مثال: العنوان متبوعاً بـ `&lat=36.7538&lon=3.0588`. GET أو POST أو JSON تصلح.
3. النقطة تُسجَّل دائماً على بطاقة الحافلة. إذا وُجدت رحلة **في الطريق**، وإلا **ركوب**، تُنسخ النقطة نفسها إليها. البطاقتان تعرضان آخر خط عرض وآخر خط طول والساعة.
4. الجواب `200` و`ok`: النقطة سُجّلت، حتى بلا رحلة مفتوحة. `409`: إحداثيات غير مقروءة أو خارج الحدود (−90..90، −180..180). `404`: رمز مجهول.
5. شبكة 4G نفسها التي يستعملها قارئ الباب تكفي. إذا انقطع الشبكة في تلك اللحظة، يجب أن يعيد الجهاز الإرسال لاحقاً. أودو لا يتصل بجهاز GPS. هو ينتظر النداء.
6. زر **Suivi GPS** على الرحلة يفتح فقط خريطة آخر نقطة وصلت (Leaflet وOpenStreetMap، إذن شاشة الإدارة تحتاج إلى الإنترنت). لا أحد يرسل موقعاً من هذه الصفحة.

رمز الحافلة سر. من يملكه يستطيع إرسال موقعاً كاذباً أو مسحاً. لا تضعه في صفحة البيع.

## قائمة الانتظار

الزر العام يظهر فقط عندما تعرض الرحلة 0 مقعد حر. التسجيل ينشئ `ATT/السنة/....`.

عرض واحد نشط لكل رحلة. يذهب إلى أول شخص في الانتظار يتسع عدد مقاعده في المقاعد الفردية الحرة (احتياط الشركات يبقى محمياً). العرض يدوم `transport.hold_minutes`. المهمة المجدولة **Transport : libérer les réservations expirées** تعمل كل 5 دقائق: تلغي الحجوزات المنتهية، وتنهي العروض المتأخرة، ثم تعرض المقعد للتالي. أودو يجب أن يبقى شغالاً حتى تنطلق المهمة.

قبول العرض ينشئ حجزاً معلقاً. المقعد لا يُؤكد إلا عند الدفع.

## البريد

القوالب كلها في الطابور (`force_send=False`):

- التذكرة المصدرة، إذا وُجد عنوان؛
- التأخر وعودة الجدول؛
- نقل التذكرة إلى رحلة أخرى؛
- عرض قائمة الانتظار؛
- إغلاق يوم العمل.

من دون خادم بريد صادر (الإعدادات → التقني → خوادم البريد الصادر) ومن دون مهمة طابور البريد، تبقى الرسالة داخل أودو. اضبط `web.base.url` قبل الإرسال، وإلا تشير الروابط إلى `localhost`.

## النتيجة والإحصاء والكشف

- تبويب **النتيجة** في الرحلة: المقاعد المباعة (مؤكدة، ركب، لم يحضر)، المحصّل، المسترد، نسبة الامتلاء لكل مقطع، الوقود، الطريق السيار، السائق، الهامش. الهامش يساوي المحصّل − المسترد − التكاليف.
- **الاستغلال → الإحصاء**: على فترة، لكل خط، المقاعد المباعة، المقاعد المعروضة، الامتلاء، الانتظار، الهامش، أهم مسار. ربح الفترة هو مجموع هوامش الرحلات غير الملغاة.
- الاقتراحات تقرأ هذه الأرقام. هي لا تستدعي نموذجاً خارجياً. امتلاء ≥ 75٪ أو شخصان على الأقل في الانتظار: اقتراح رحلة إضافية على المسار الأكثر بيعاً. امتلاء ≤ 40٪ وحافلة في الأسطول تغطي ذروة البيع بمقاعد أقل من الخط: اقتراح تلك الحافلة. لا اقتراح يخترع خطاً لم يُبع قط.
- **الشركات → الكشف الشهري**، أو زر **Relevé** على العقد: PDF لرحلات المشتركين المؤكدة أو التي ركب أصحابها أو لم يحضروا، خلال الفترة. التذييل يقول إن هذا ليس فاتورة.

## إغلاق يوم عمل

**الاستغلال → Fermer une journée**، أو الزر على الخط. السبب إلزامي. خط فارغ يعني كل الخطوط.

اليوم المختار يلغي الرحلات المخططة والمعيَّنة والتي في الركوب. التذاكر المدفوعة على هذه الرحلات تُسترد كاملة. قائمة انتظارها تُلغى. رحلة **في الطريق** تبقى. رحلة فيها راكب صعد من قبل تُحفظ. الأيام الأخرى لا تتغير.

## الترقيم

| المستند | الشكل |
| --- | --- |
| الرحلة | `DEP/2026/0001` |
| الحجز | `RES/2026/0001` |
| العقد | `CTR/2026/0001` |
| قائمة الانتظار | `ATT/2026/0001` |

## أعطال سريعة

| العَرض | السبب المعتاد |
| --- | --- |
| لا قائمة Transport | المستخدم ليس Dispatch ولا Responsable. |
| « Ce trajet n'a pas de prix. » | لا تعرفة لهذا الصعود وهذا النزول. |
| التعيين مرفوض | الحافلة، أو السائق، أو إحدى التأهيلات الثلاث ناقصة أو منتهية قبل يوم الرحلة. |
| التعيين التلقائي مرفوض | لا مسافة على الخط، أو لا سائق على هذا الخط، أو لا حافلة بالحجم المناسب وبمقاعد كافية وحرة، أو السائق في الطريق، أو أكثر من 8 ساعات قيادة في ذلك اليوم. |
| الانطلاق مرفوض | نقطة مراقبة حرجة ليست مطابقة. |
| QR لا يمر | النص ناقص، أو الرحلة أخرى، أو التذكرة غير مؤكدة، أو `transport.qr_secret` تغيّر. |
| الكاميرا لا تُفتح | الصفحة فُتحت بـ HTTP من جهاز آخر، أو رُفض الإذن. حقل QR يبقى صالحاً. استعمل HTTPS. |
| جهاز GPS لا يرسل | العنوان المنسوخ على الحافلة غير قابل للوصول، أو الرمز خاطئ، أو المعاملات ليست `lat`/`lon`. |
| الخريطة فارغة | لا إنترنت نحو unpkg أو OpenStreetMap، أو لم تُرسل أي نقطة. |
| حروف PDF غريبة | PDF قديم، أو wkhtmltopdf غير مثبت. أعد التوليد بعد التحديث. الخط المفروض هو Arial. |
| البريد لا يصل | لا خادم صادر، أو الراكب بلا عنوان. |
| الصفحة العامة تطلب اسم القاعدة | أضف `?db=DATABASE`. |
| رحلات الأمس تظهر في اليوم | حدّث التطبيق. المرشح هو `service_date`، وليس المرشح القديم « مفتوح ». |

</div>
