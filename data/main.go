package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"

	"github.com/google/uuid"
)

type Post struct {
	Title    string `json:"title"`
	Category string `json:"category"`
	Question string `json:"question"`
	Answer   string `json:"answer"`
}

type Root struct {
	Posts []Post `json:"posts"`
}

func main_readCategory() {
	// JSONファイルを読み込む
	data, err := os.ReadFile("exportjson.json")
	if err != nil {
		panic(err)
	}

	var root Root
	if err := json.Unmarshal(data, &root); err != nil {
		panic(err)
	}

	// 重複排除用
	categorySet := make(map[string]struct{})

	for _, post := range root.Posts {
		if post.Category != "" {
			categorySet[post.Category] = struct{}{}
		}
	}

	// 出力
	for category := range categorySet {
		fmt.Println(category)
	}
}

func showMissingGUIDsOnJSON(csvFile, jsonFile string) error {
	f, err := os.Open(csvFile)
	if err != nil {
		return err
	}
	defer f.Close()

	r := csv.NewReader(f)
	records, err := r.ReadAll()
	if err != nil {
		return err
	}
	if len(records) == 0 {
		return fmt.Errorf("CSVファイルが空です: %s", csvFile)
	}

	guidIndex := -1
	for i, h := range records[0] {
		if strings.TrimSpace(h) == "qa_id" {
			guidIndex = i
			break
		}
	}
	if guidIndex == -1 {
		return fmt.Errorf("qa_id列が見つかりません: %s", csvFile)
	}

	csvGUIDs := make(map[string]struct{})
	for _, rec := range records[1:] {
		if guidIndex >= len(rec) {
			continue
		}
		guid := strings.TrimSpace(rec[guidIndex])
		if guid != "" {
			csvGUIDs[guid] = struct{}{}
		}
	}

	jsonData, err := os.ReadFile(jsonFile)
	if err != nil {
		return err
	}

	var items []map[string]interface{}
	if err := json.Unmarshal(jsonData, &items); err != nil {
		return err
	}

	jsonGUIDs := make(map[string]struct{})
	for _, item := range items {
		if guidValue, ok := item["guid"]; ok {
			if guid, ok := guidValue.(string); ok && guid != "" {
				jsonGUIDs[guid] = struct{}{}
			}
		}
	}

	missing := make([]string, 0)
	for guid := range csvGUIDs {
		if _, exists := jsonGUIDs[guid]; !exists {
			missing = append(missing, guid)
		}
	}

	sort.Strings(missing)
	if len(missing) == 0 {
		fmt.Println("CSVには存在するがJSONには存在しないGUIDはありませんでした。")
		return nil
	}

	for _, guid := range missing {
		fmt.Println(guid)
	}
	fmt.Printf("CSVには存在するがJSONには存在しないGUIDの数: %d\n", len(missing))
	return nil
}

func showMissingGUIDsOnCSV(csvFile, jsonFile string) error {
	f, err := os.Open(csvFile)
	if err != nil {
		return err
	}
	defer f.Close()

	r := csv.NewReader(f)
	records, err := r.ReadAll()
	if err != nil {
		return err
	}
	if len(records) == 0 {
		return fmt.Errorf("CSVファイルが空です: %s", csvFile)
	}

	guidIndex := -1
	for i, h := range records[0] {
		if strings.TrimSpace(h) == "qa_id" {
			guidIndex = i
			break
		}
	}
	if guidIndex == -1 {
		return fmt.Errorf("qa_id列が見つかりません: %s", csvFile)
	}

	csvGUIDs := make(map[string]struct{})
	for _, rec := range records[1:] {
		if guidIndex >= len(rec) {
			continue
		}
		guid := strings.TrimSpace(rec[guidIndex])
		if guid != "" {
			csvGUIDs[guid] = struct{}{}
		}
	}

	jsonData, err := os.ReadFile(jsonFile)
	if err != nil {
		return err
	}

	var items []map[string]interface{}
	if err := json.Unmarshal(jsonData, &items); err != nil {
		return err
	}

	jsonGUIDs := make(map[string]struct{})
	for _, item := range items {
		if guidValue, ok := item["guid"]; ok {
			if guid, ok := guidValue.(string); ok && guid != "" {
				jsonGUIDs[guid] = struct{}{}
			}
		}
	}

	missing := make([]string, 0)
	for guid := range jsonGUIDs {
		if _, exists := csvGUIDs[guid]; !exists {
			missing = append(missing, guid)
		}
	}

	sort.Strings(missing)
	if len(missing) == 0 {
		fmt.Println("JSONには存在するがCSVには存在しないGUIDはありませんでした。")
		return nil
	}

	for _, guid := range missing {
		fmt.Println(guid)
	}
	fmt.Printf("JSONには存在するがCSVには存在しないGUIDの数: %d\n", len(missing))
	return nil
}

func showNonConsecutiveGUIDsInCSV(csvFile string) error {
	f, err := os.Open(csvFile)
	if err != nil {
		return err
	}
	defer f.Close()

	r := csv.NewReader(f)
	records, err := r.ReadAll()
	if err != nil {
		return err
	}
	if len(records) == 0 {
		return fmt.Errorf("CSVファイルが空です: %s", csvFile)
	}

	guidIndex := -1
	for i, h := range records[0] {
		if strings.TrimSpace(h) == "qa_id" {
			guidIndex = i
			break
		}
	}
	if guidIndex == -1 {
		return fmt.Errorf("qa_id列が見つかりません: %s", csvFile)
	}

	seen := make(map[string]struct{})
	nonConsecutive := make(map[string]struct{})
	lastGUID := ""

	for _, rec := range records[1:] {
		if guidIndex >= len(rec) {
			continue
		}
		guid := strings.TrimSpace(rec[guidIndex])
		if guid == "" {
			continue
		}
		if guid != lastGUID {
			if _, exists := seen[guid]; exists {
				nonConsecutive[guid] = struct{}{}
			}
		}
		seen[guid] = struct{}{}
		lastGUID = guid
	}

	if len(nonConsecutive) == 0 {
		fmt.Println("連続せずに登録されているGUIDはありませんでした。")
		return nil
	}

	missing := make([]string, 0, len(nonConsecutive))
	for guid := range nonConsecutive {
		missing = append(missing, guid)
	}
	sort.Strings(missing)
	for _, guid := range missing {
		fmt.Println(guid)
	}
	fmt.Printf("連続せずに登録されているGUIDの数: %d\n", len(nonConsecutive))
	return nil
}

func main() {
	fmt.Println("CSVには存在するがJSONには存在しないGUID:")
	if err := showMissingGUIDsOnJSON("question_altered.csv", "exportjson_withguid.json"); err != nil {
		fmt.Println("エラー:", err)
	}
	fmt.Println("JSONには存在するがCSVには存在しないGUID:")
	if err := showMissingGUIDsOnCSV("question_altered.csv", "exportjson_withguid.json"); err != nil {
		fmt.Println("エラー:", err)
	}
	fmt.Println("CSVに連続せずに登録されているGUID:")
	if err := showNonConsecutiveGUIDsInCSV("question_altered.csv"); err != nil {
		fmt.Println("エラー:", err)
	}
	// fmt.Println("CSV内でtextが重複したGUID:")
	// if err := showGUIDsWithSameTextDifferentGUIDs("question_altered.csv"); err != nil {
	// 	fmt.Println("エラー:", err)
	// }
}

func showGUIDsWithSameTextDifferentGUIDs(csvFile string) error {
	f, err := os.Open(csvFile)
	if err != nil {
		return err
	}
	defer f.Close()

	r := csv.NewReader(f)
	records, err := r.ReadAll()
	if err != nil {
		return err
	}
	if len(records) == 0 {
		return fmt.Errorf("CSVファイルが空です: %s", csvFile)
	}

	guidIndex := -1
	textIndex := -1
	for i, h := range records[0] {
		switch strings.TrimSpace(h) {
		case "qa_id":
			guidIndex = i
		case "text":
			textIndex = i
		}
	}
	if guidIndex == -1 {
		return fmt.Errorf("qa_id列が見つかりません: %s", csvFile)
	}
	if textIndex == -1 {
		return fmt.Errorf("text列が見つかりません: %s", csvFile)
	}

	// map[text] -> set of GUIDs
	textToGUIDs := make(map[string]map[string]struct{})

	for _, rec := range records[1:] {
		if guidIndex >= len(rec) || textIndex >= len(rec) {
			continue
		}
		guid := strings.TrimSpace(rec[guidIndex])
		text := strings.TrimSpace(rec[textIndex])
		if guid == "" || text == "" {
			continue
		}
		set, ok := textToGUIDs[text]
		if !ok {
			set = make(map[string]struct{})
			textToGUIDs[text] = set
		}
		set[guid] = struct{}{}
	}

	// collect texts that map to multiple GUIDs
	type dupEntry struct {
		text  string
		guids []string
	}
	duplicates := make([]dupEntry, 0)
	for text, gids := range textToGUIDs {
		if len(gids) > 1 {
			list := make([]string, 0, len(gids))
			for g := range gids {
				list = append(list, g)
			}
			sort.Strings(list)
			duplicates = append(duplicates, dupEntry{text: text, guids: list})
		}
	}

	if len(duplicates) == 0 {
		fmt.Println("同じtextが異なるGUIDで登録されているものはありませんでした。")
		return nil
	}

	// sort by text for stable output
	sort.Slice(duplicates, func(i, j int) bool { return duplicates[i].text < duplicates[j].text })

	for _, d := range duplicates {
		fmt.Println("-----")
		fmt.Println("text:", d.text)
		for _, g := range d.guids {
			fmt.Println(g)
		}
	}
	fmt.Printf("同じtextで複数GUIDが登録されている件数: %d\n", len(duplicates))
	return nil
}

func main_gen_guid() {
	//func main_uuid() {
	inputFile := "exportjson.json"
	outputFile := "exportjson_guid.json"

	// ファイル読み込み
	data, err := os.ReadFile(inputFile)
	if err != nil {
		panic(err)
	}

	// JSONパース（配列想定）
	var records []map[string]interface{}
	var root Root
	if err := json.Unmarshal(data, &root); err != nil {
		panic(err)
	}

	// 各オブジェクトにGUIDを付与
	for _, post := range root.Posts {
		rec := make(map[string]interface{})
		rec["title"] = post.Title
		rec["category"] = post.Category
		rec["question"] = post.Question
		rec["answer"] = post.Answer
		rec["guid"] = uuid.New().String()
		records = append(records, rec)
	}

	// JSONとして整形（インデント付き）
	out, err := json.MarshalIndent(records, "", "  ")
	if err != nil {
		panic(err)
	}

	// ファイル出力
	if err := os.WriteFile(outputFile, out, 0644); err != nil {
		panic(err)
	}

	fmt.Println("完了:", outputFile)
}
