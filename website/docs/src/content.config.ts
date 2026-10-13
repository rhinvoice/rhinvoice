import { docsLoader, i18nLoader } from "@astrojs/starlight/loaders";
import { docsSchema, i18nSchema } from "@astrojs/starlight/schema";
import { defineCollection } from "astro:content";
import { z } from "astro/zod";

export const collections = {
  // Interface words of the docs that differ from Starlight's own translations.
  i18n: defineCollection({ loader: i18nLoader(), schema: i18nSchema() }),
  docs: defineCollection({
    loader: docsLoader(),
    schema: docsSchema({
      extend: z.object({
        /**
         * Questions and answers of the page: shown by <Faq /> and given to search
         * engines as FAQPage data, so both always say the same.
         */
        faq: z.array(z.object({ q: z.string(), a: z.string() })).optional(),
        /** The version that brought the page's feature, shown under the title (e.g. "0.5.0"). */
        since: z
          .string()
          .regex(/^\d+\.\d+\.\d+$/)
          .optional(),
      }),
    }),
  }),
};
