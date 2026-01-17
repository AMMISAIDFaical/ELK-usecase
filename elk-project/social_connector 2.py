import argparse
import dataclasses
import logging
import os
import time
from typing import Iterable, Optional

import gridfs
import requests
from pymongo import MongoClient


DEFAULT_GRAPH_API_VERSION = "v18.0"
DEFAULT_MONGO_DB = "social_media"
DEFAULT_MONGO_URI = "mongodb://localhost:27017"


@dataclasses.dataclass
class SocialPost:
    platform: str
    post_id: str
    text: str
    created_time: Optional[str]
    image_url: Optional[str]
    comments: list[dict]
    raw: dict


class GraphAPIClient:
    def __init__(self, access_token: str, api_version: str = DEFAULT_GRAPH_API_VERSION) -> None:
        self.access_token = access_token
        self.base_url = f"https://graph.facebook.com/{api_version}"
        self.session = requests.Session()

    def get(self, path: str, params: dict) -> dict:
        url = f"{self.base_url}/{path.lstrip('/')}"
        response = self.session.get(url, params={**params, "access_token": self.access_token}, timeout=20)
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise RuntimeError(payload["error"])
        return payload

    def iter_pages(self, path: str, params: dict, limit: int) -> Iterable[dict]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        next_params = {**params, "access_token": self.access_token}
        fetched = 0
        while url and fetched < limit:
            response = self.session.get(url, params=next_params, timeout=20)
            response.raise_for_status()
            payload = response.json()
            if "error" in payload:
                raise RuntimeError(payload["error"])
            for item in payload.get("data", []):
                yield item
                fetched += 1
                if fetched >= limit:
                    break
            url = payload.get("paging", {}).get("next")
            next_params = None


class MongoStore:
    def __init__(self, mongo_uri: str, db_name: str) -> None:
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.posts = self.db.social_posts
        self.fs = gridfs.GridFS(self.db, collection="images")
        self.posts.create_index([("platform", 1), ("post_id", 1)], unique=True)
        self.posts.create_index([("subject", 1), ("created_time", -1)])

    def upsert_post(self, subject: str, post: SocialPost, image_bytes: Optional[bytes]) -> None:
        query = {"platform": post.platform, "post_id": post.post_id}
        existing = self.posts.find_one(query, {"image_gridfs_id": 1})
        image_gridfs_id = existing.get("image_gridfs_id") if existing else None
        if image_bytes and not image_gridfs_id:
            image_gridfs_id = self.fs.put(
                image_bytes,
                filename=f"{post.platform}_{post.post_id}.jpg",
                metadata={"platform": post.platform, "post_id": post.post_id, "subject": subject},
            )
        payload = {
            "platform": post.platform,
            "post_id": post.post_id,
            "subject": subject,
            "text": post.text,
            "created_time": post.created_time,
            "image_url": post.image_url,
            "image_gridfs_id": image_gridfs_id,
            "comments": post.comments,
            "raw": post.raw,
        }
        self.posts.update_one(query, {"$set": payload}, upsert=True)


def text_matches_subject(text: Optional[str], subject: str) -> bool:
    if not text:
        return False
    return subject.lower() in text.lower()


def download_image(url: str) -> Optional[bytes]:
    if not url:
        return None
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.content


class FacebookConnector:
    def __init__(self, access_token: str, page_id: str) -> None:
        self.client = GraphAPIClient(access_token)
        self.page_id = page_id

    def fetch_posts(self, subject: str, limit: int = 50) -> list[SocialPost]:
        fields = (
            "message,created_time,full_picture,attachments{media_type,media},"
            "comments.limit(25){message,created_time,from}"
        )
        params = {"fields": fields, "limit": min(limit, 100)}
        posts = []
        for item in self.client.iter_pages(f"{self.page_id}/posts", params, limit):
            text = item.get("message", "")
            if not text_matches_subject(text, subject):
                continue
            image_url = item.get("full_picture") or _extract_facebook_attachment(item)
            comments = [
                {
                    "message": comment.get("message", ""),
                    "created_time": comment.get("created_time"),
                    "from": (comment.get("from") or {}).get("name"),
                }
                for comment in item.get("comments", {}).get("data", [])
            ]
            posts.append(
                SocialPost(
                    platform="facebook",
                    post_id=item["id"],
                    text=text,
                    created_time=item.get("created_time"),
                    image_url=image_url,
                    comments=comments,
                    raw=item,
                )
            )
        return posts


class InstagramConnector:
    def __init__(self, access_token: str, user_id: str) -> None:
        self.client = GraphAPIClient(access_token)
        self.user_id = user_id

    def fetch_posts(self, subject: str, limit: int = 50) -> list[SocialPost]:
        params = {
            "fields": "id,caption,media_type,media_url,timestamp,children",
            "limit": min(limit, 100),
        }
        posts = []
        for item in self.client.iter_pages(f"{self.user_id}/media", params, limit):
            caption = item.get("caption", "")
            if not text_matches_subject(caption, subject):
                continue
            image_url = item.get("media_url")
            if item.get("media_type") == "CAROUSEL_ALBUM":
                image_url = image_url or _fetch_instagram_carousel_image(self.client, item.get("id"))
            comments = _fetch_instagram_comments(self.client, item.get("id"))
            posts.append(
                SocialPost(
                    platform="instagram",
                    post_id=item["id"],
                    text=caption,
                    created_time=item.get("timestamp"),
                    image_url=image_url,
                    comments=comments,
                    raw=item,
                )
            )
        return posts


def _extract_facebook_attachment(item: dict) -> Optional[str]:
    attachments = item.get("attachments", {}).get("data", [])
    for attachment in attachments:
        media = attachment.get("media", {}).get("image", {}).get("src")
        if media:
            return media
    return None


def _fetch_instagram_comments(client: GraphAPIClient, media_id: Optional[str]) -> list[dict]:
    if not media_id:
        return []
    params = {"fields": "text,timestamp,username", "limit": 25}
    comments = []
    for item in client.iter_pages(f"{media_id}/comments", params, limit=25):
        comments.append(
            {"message": item.get("text", ""), "created_time": item.get("timestamp"), "from": item.get("username")}
        )
    return comments


def _fetch_instagram_carousel_image(client: GraphAPIClient, media_id: Optional[str]) -> Optional[str]:
    if not media_id:
        return None
    params = {"fields": "children{media_url,media_type}"}
    payload = client.get(f"{media_id}", params)
    for child in payload.get("children", {}).get("data", []):
        if child.get("media_type") == "IMAGE" and child.get("media_url"):
            return child["media_url"]
    return None


def collect_posts(subject: str, limit: int, facebook: bool, instagram: bool) -> list[SocialPost]:
    posts = []
    if facebook:
        fb_token = os.getenv("FB_ACCESS_TOKEN")
        fb_page_id = os.getenv("FB_PAGE_ID")
        if not fb_token or not fb_page_id:
            raise RuntimeError("FB_ACCESS_TOKEN and FB_PAGE_ID are required for Facebook collection.")
        posts.extend(FacebookConnector(fb_token, fb_page_id).fetch_posts(subject, limit=limit))
    if instagram:
        ig_token = os.getenv("IG_ACCESS_TOKEN")
        ig_user_id = os.getenv("IG_USER_ID")
        if not ig_token or not ig_user_id:
            raise RuntimeError("IG_ACCESS_TOKEN and IG_USER_ID are required for Instagram collection.")
        posts.extend(InstagramConnector(ig_token, ig_user_id).fetch_posts(subject, limit=limit))
    return posts


def run(subject: str, limit: int, mongo_uri: str, mongo_db: str, facebook: bool, instagram: bool) -> None:
    logging.info("Collecting posts about '%s'", subject)
    posts = collect_posts(subject, limit=limit, facebook=facebook, instagram=instagram)
    store = MongoStore(mongo_uri, mongo_db)
    for post in posts:
        image_bytes = download_image(post.image_url) if post.image_url else None
        store.upsert_post(subject, post, image_bytes)
        time.sleep(0.2)
    logging.info("Stored %d posts in MongoDB (%s).", len(posts), mongo_db)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect Facebook/Instagram posts and store in MongoDB.")
    parser.add_argument("--subject", required=True, help="Topic to filter posts (case-insensitive substring match).")
    parser.add_argument("--limit", type=int, default=50, help="Max posts per platform to inspect.")
    parser.add_argument("--mongo-uri", default=DEFAULT_MONGO_URI)
    parser.add_argument("--mongo-db", default=DEFAULT_MONGO_DB)
    parser.add_argument("--facebook", action="store_true", help="Collect Facebook page posts.")
    parser.add_argument("--instagram", action="store_true", help="Collect Instagram user posts.")
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = build_parser()
    args = parser.parse_args()
    if not args.facebook and not args.instagram:
        args.facebook = True
        args.instagram = True
    run(args.subject, args.limit, args.mongo_uri, args.mongo_db, args.facebook, args.instagram)


if __name__ == "__main__":
    main()
