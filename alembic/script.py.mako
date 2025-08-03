"""
This is a template used by Alembic to generate migration scripts. It
includes simple structure with upgrade and downgrade functions.
"""

<%text># coding: utf-8
"""${message}

Revision ID: ${revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "${revision}"
down_revision = "${down_revision}"
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else 'pass'}


def downgrade() -> None:
    ${downgrades if downgrades else 'pass'}
</%text>

