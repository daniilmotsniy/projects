from typing import List

from sqlalchemy.orm import joinedload
from ...models.pd.base import PromptTagBaseModel
from ...utils.constants import PROMPT_LIB_MODE
from ...utils.create_utils import create_version
from ...utils.prompt_utils import list_prompts
from ...utils.prompt_utils_legacy import prompts_create_prompt
from flask import request, g
from pylon.core.tools import web, log
from tools import api_tools, config as c, db, auth

from pydantic import ValidationError
from ...models.all import Prompt
from ...models.pd.create import PromptCreateModel
from ...models.pd.detail import PromptDetailModel, PromptVersionDetailModel
from ...models.pd.list import PromptListModel, PromptTagListModel
import json


class ProjectAPI(api_tools.APIModeHandler):
    @auth.decorators.check_api(
        {
            "permissions": ["models.prompts.prompts.list"],
            "recommended_roles": {
                c.ADMINISTRATION_MODE: {"admin": True, "editor": True, "viewer": False},
                c.DEFAULT_MODE: {"admin": True, "editor": True, "viewer": False},
            },
        }
    )
    def get(self, project_id):
        log.info("Getting all prompts for project %s", project_id)
        with_versions = request.args.get("versions", "").lower() == "true"
        prompts = self.module.get_all(project_id, with_versions)

        return prompts

    @auth.decorators.check_api(
        {
            "permissions": ["models.prompts.prompts.create"],
            "recommended_roles": {
                c.ADMINISTRATION_MODE: {"admin": True, "editor": True, "viewer": False},
                c.DEFAULT_MODE: {"admin": True, "editor": True, "viewer": False},
            },
        }
    )
    def post(self, project_id):
        try:
            prompt = prompts_create_prompt(project_id, dict(request.json))
            return prompt, 201
        except ValidationError as e:
            return e.errors(), 400


class PromptLibAPI(api_tools.APIModeHandler):
    def _get_project_id(self, project_id: int | None) -> int:
        if not project_id:
            project_id = 0  # todo: get user personal project id here
        return project_id

    def get(self, project_id: int | None = None, **kwargs):
        project_id = self._get_project_id(project_id)
        # list prompts
        total, prompts = list_prompts(project_id, request.args)
        # parsing
        all_authors = set()
        parsed: List[PromptListModel] = []
        for i in prompts:
            p = PromptListModel.from_orm(i)
            # p.author_ids = set()
            tags = dict()
            for v in i.versions:
                for t in v.tags:
                    tags[t.name] = PromptTagListModel.from_orm(t).dict()
                p.author_ids.add(v.author_id)
                all_authors.update(p.author_ids)
            p.tags = list(tags.values())
            parsed.append(p)

        users = auth.list_users(user_ids=list(all_authors))
        user_map = {i["id"]: i for i in users}

        for i in parsed:
            i.set_authors(user_map)

        return {
            "rows": [json.loads(i.json(exclude={"author_ids"})) for i in parsed],
            "total": total
        },  200

    def post(self, project_id: int | None = None, **kwargs):
        project_id = self._get_project_id(project_id)

        raw = dict(request.json)
        raw["owner_id"] = project_id
        for version in raw.get("versions", []):
            version["author_id"] = g.auth.id
        try:
            prompt_data = PromptCreateModel.parse_obj(raw)
        except ValidationError as e:
            return e.errors(), 400

        with db.with_project_schema_session(project_id) as session:
            prompt = Prompt(
                **prompt_data.dict(exclude_unset=True, exclude={"versions"})
            )

            for ver in prompt_data.versions:
                create_version(ver, prompt=prompt, session=session)
            session.add(prompt)
            session.commit()

            result = PromptDetailModel.from_orm(prompt)
            result.version_details = PromptVersionDetailModel.from_orm(
                prompt.versions[0]
            )
            result.version_details.author = auth.get_user(
                user_id=result.version_details.author_id
            )
            return json.loads(result.json()), 201


class API(api_tools.APIBase):
    url_params = api_tools.with_modes(
        [
            "",
            "<int:project_id>",
        ]
    )

    mode_handlers = {
        c.DEFAULT_MODE: ProjectAPI,
        PROMPT_LIB_MODE: PromptLibAPI,
    }
