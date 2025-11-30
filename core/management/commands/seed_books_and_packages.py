# core/management/commands/seed_books_and_packages.py

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils.text import slugify
from core.models import CoinPackage, Book
import os


class Command(BaseCommand):
    def handle(self, *args, **options):
        self.stdout.write("Starting database seeding...")

        # === 1. ENSURE ADMIN USER EXISTS ===
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@zerobookswap.com',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        if created:
            admin_user.set_password('admin123')  # change later
            admin_user.save()
            self.stdout.write(self.style.SUCCESS("Created admin user: admin / admin123"))

        # ==============================
        # 1. Create Coin Packages
        # ==============================
        packages = [
            {'name': 'Starter Pack',  'zcoin_amount': 1000,  'price_birr': 10},
            {'name': 'Standard Pack', 'zcoin_amount': 5000,  'price_birr': 45},
            {'name': 'Premium Pack',  'zcoin_amount': 10000, 'price_birr': 80},
            {'name': 'Mega Pack',     'zcoin_amount': 25000, 'price_birr': 180},
            {'name': 'Ultra Pack',     'zcoin_amount': 50000, 'price_birr': 300},
            {'name': 'Giga Pack',     'zcoin_amount': 100000, 'price_birr': 500},
        ]

        for pkg_data in packages:
            pkg, created = CoinPackage.objects.get_or_create(
                name=pkg_data['name'],
                defaults=pkg_data
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created CoinPackage: {pkg.name}"))

        # ==============================
        # 2. Static Swap Books
        # ==============================
        swap_books = [
            {"title": "The Theory of Everything", "author": "Stephen Hawking", "genre": "non-fiction", "zcoin_value": 46000, "cover": "assets/the-theory-of-everything.png"},
            {"title": "Success From Anywhere", "author": "Karen Mangia", "genre": "classics", "zcoin_value": 39900, "cover": "assets/success-from-anywhere.png"},
            {"title": "Promote Yourself to a Better Job", "author": "Phillp Parrish", "genre": "fiction", "zcoin_value": 21250, "cover": "assets/promote-yourself-to-a-better-job.png"},
            {"title": "Prescription for Total Wealth", "author": "Dr. Sanjoy Mukersit", "genre": "classics", "zcoin_value": 92000, "cover": "assets/prescription-for-total-wealth.png"},
            {"title": "Leningrad and its Environs", "author": "J.D. Salinger", "genre": "fiction", "zcoin_value": 94500, "cover": "assets/leningrad-and-its-environs.png"},
            {"title": "Lead The Way Five Minutes A Day", "author": "Jo Anna Preston", "genre": "non-fiction", "zcoin_value": 42750, "cover": "assets/lead-the-way-five-minutes-a-day.png"},
            {"title": "An Inside View", "author": "Edward Boorstain", "genre": "non-fiction", "zcoin_value": 63000, "cover": "assets/an-inside-view.png"},
            {"title": "ውብ", "author": "ደሴ አዳም", "genre": "contemporary", "zcoin_value": 13586, "cover": "assets/wib.png"},
            {"title": "የሱፍ አበባ", "author": "ሃብታሙ አለማየሁ", "genre": "fiction", "zcoin_value": 3836, "cover": "assets/yesuf-abeba.png"},
            {"title": "The Sales Manager's Handbook", "author": "Joseph C. Ellers", "genre": "non-fiction", "zcoin_value": 210000, "cover": "assets/the-sales-managers-handbook.png"},
        ]

        for book in swap_books:
            obj, created = Book.objects.update_or_create(
                added_by=admin_user,
                title=book["title"],
                author=book["author"],
                defaults={
                    "genre": book["genre"],
                    "book_type": "swap",
                    "price_birr": 25,
                    "zcoin_value": book["zcoin_value"],
                    "cover_image_url": book["cover"],
                    "is_available": True,
                    "slug": slugify(book["title"][:50] + "-" + book["author"][:20])

                }
            )
            status = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{status} Swap Book: {obj.title} by {obj.author}"))

        # ==============================
        # 3. Static New Books
        # ==============================
        new_books = [
            {"title": "Start with Why", "author": "Simon Sinek", "genre": "contemporary", "price_birr": 650, "cover": "assets/start-with-why.png"},
            {"title": "The Power of Positive Thinking", "author": "Norman Vincent Peale", "genre": "non-fiction", "price_birr": 480, "cover": "assets/the-power-of-positive-thinking.png"},
            {"title": "Oromay", "author": "Bealu Girma", "genre": "fiction", "price_birr": 400, "cover": "assets/oromay.png"},
            {"title": "Never Eat Alone", "author": "Keith Ferrazzi", "genre": "non-fiction", "price_birr": 650, "cover": "assets/never-eat-alone.png"},
            {"title": "Atomic Habit", "author": "James Clear", "genre": "contemporary", "price_birr": 700, "cover": "assets/atomic-habit.png"},
            {"title": "ሕማማት", "author": "ዲያቆን ሄኖክ ኃይሌ", "genre": "non-fiction", "price_birr": 520, "cover": "assets/himamat.png"},
            {"title": "Zero to One", "author": "Peter Thiel", "genre": "non-fiction", "price_birr": 430, "cover": "assets/zero-to-one.png"},
            {"title": "You Can Win", "author": "Shiv Khera", "genre": "non-fiction", "price_birr": 380, "cover": "assets/you-can-win.png"},
        ]

        for book in new_books:
            obj, created = Book.objects.update_or_create(
                added_by=admin_user,
                title=book["title"],
                author=book["author"],
                defaults={
                    "genre": book["genre"],
                    "book_type": "new",
                    "price_birr": book["price_birr"],
                    "zcoin_value": 0,
                    "cover_image_url": book["cover"],
                    "is_available": True,
                    "slug": slugify(book["title"][:50] + "-" + book["author"][:20])

                }
            )
            status = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{status} New Book: {obj.title} by {obj.author}"))

        self.stdout.write(self.style.SUCCESS("Database seeding completed successfully!"))