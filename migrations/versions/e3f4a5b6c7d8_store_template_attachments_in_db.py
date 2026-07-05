"""store template attachments in db

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-03-13 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import os


# revision identifiers, used by Alembic.
revision = 'e3f4a5b6c7d8'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add file_content column (nullable initially so we can migrate data)
    op.add_column('template_attachments', sa.Column('file_content', sa.LargeBinary(), nullable=True))

    # Migrate existing file data from disk into the new column
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, file_path FROM template_attachments")).fetchall()
    for row in rows:
        file_path = row[1]
        if file_path and os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                content = f.read()
            conn.execute(
                sa.text("UPDATE template_attachments SET file_content = :content WHERE id = :id"),
                {"content": content, "id": row[0]}
            )

    # Make file_content NOT NULL now that data is migrated
    op.alter_column('template_attachments', 'file_content', nullable=False)

    # Drop the file_path column
    op.drop_column('template_attachments', 'file_path')


def downgrade() -> None:
    # Re-add file_path column
    op.add_column('template_attachments', sa.Column('file_path', sa.String(1024), nullable=True))

    # We can't restore files to disk in downgrade, so just set a placeholder path
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE template_attachments SET file_path = 'migrated_to_db'"))

    op.alter_column('template_attachments', 'file_path', nullable=False)

    # Drop file_content column
    op.drop_column('template_attachments', 'file_content')
