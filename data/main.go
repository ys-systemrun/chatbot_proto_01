package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
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

	// JSONとCSVをGUIDでマージして出力
	if err := mergeJSONAndCSVToCSV("exportjson_withguid.json", "question_altered.csv", "merged_output.csv"); err != nil {
		fmt.Println("マージエラー:", err)
	}

	// // JSONをGUIDでソートして出力
	// if err := sortJSONByGUID("exportjson_withguid.json", "exportjson_withguid_sorted.json"); err != nil {
	// 	fmt.Println("JSONソートエラー:", err)
	// }
	// // CSVをGUIDでソートして出力
	// if err := sortCSVByGUID("question_altered.csv", "question_altered_sorted.csv"); err != nil {
	// 	fmt.Println("CSVソートエラー:", err)
	// }
	// fmt.Println("CSVには存在するがJSONには存在しないGUID:")
	// if err := showMissingGUIDsOnJSON("question_altered.csv", "exportjson_withguid.json"); err != nil {
	// 	fmt.Println("エラー:", err)
	// }
	// fmt.Println("JSONには存在するがCSVには存在しないGUID:")
	// if err := showMissingGUIDsOnCSV("question_altered.csv", "exportjson_withguid.json"); err != nil {
	// 	fmt.Println("エラー:", err)
	// }
	// fmt.Println("CSVに連続せずに登録されているGUID:")
	// if err := showNonConsecutiveGUIDsInCSV("question_altered.csv"); err != nil {
	// 	fmt.Println("エラー:", err)
	// }
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

func sortJSONByGUID(inputFile, outputFile string) error {
	data, err := os.ReadFile(inputFile)
	if err != nil {
		return err
	}

	var items []map[string]interface{}
	if err := json.Unmarshal(data, &items); err != nil {
		return err
	}

	sort.SliceStable(items, func(i, j int) bool {
		gi, _ := items[i]["guid"].(string)
		gj, _ := items[j]["guid"].(string)
		return gi < gj
	})

	out, err := json.MarshalIndent(items, "", "  ")
	if err != nil {
		return err
	}

	return os.WriteFile(outputFile, out, 0644)
}

func sortCSVByGUID(inputFile, outputFile string) error {
	f, err := os.Open(inputFile)
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
		return fmt.Errorf("CSVファイルが空です: %s", inputFile)
	}

	guidIndex := -1
	textIndex := -1
	headers := records[0]
	for i, h := range headers {
		h = strings.TrimSpace(h)
		if h == "qa_id" {
			guidIndex = i
		}
		if h == "text" {
			textIndex = i
		}
	}
	if guidIndex == -1 {
		return fmt.Errorf("qa_id列が見つかりません: %s", inputFile)
	}

	sort.SliceStable(records[1:], func(i, j int) bool {
		gi := ""
		gj := ""
		if guidIndex < len(records[i+1]) {
			gi = strings.TrimSpace(records[i+1][guidIndex])
		}
		if guidIndex < len(records[j+1]) {
			gj = strings.TrimSpace(records[j+1][guidIndex])
		}
		return gi < gj
	})

	outFile, err := os.Create(outputFile)
	if err != nil {
		return err
	}
	defer outFile.Close()

	headerLen := len(headers)
	for _, rec := range records {
		row := make([]string, headerLen)
		for i := 0; i < headerLen; i++ {
			value := ""
			if i < len(rec) {
				value = rec[i]
			}
			if i == textIndex {
				row[i] = quoteCSVFieldAlways(value)
			} else {
				row[i] = quoteCSVField(value)
			}
		}
		if _, err := outFile.WriteString(strings.Join(row, ",") + "\n"); err != nil {
			return err
		}
	}
	return nil
}

func splitJSONByGUID(inputFile string, chunkSize int, outputDir string) error {
	if chunkSize <= 0 {
		return fmt.Errorf("chunkSize must be > 0")
	}

	data, err := os.ReadFile(inputFile)
	if err != nil {
		return err
	}

	var items []map[string]interface{}
	if err := json.Unmarshal(data, &items); err != nil {
		return err
	}

	if err := os.MkdirAll(outputDir, 0755); err != nil {
		return err
	}

	rowsByGUID := make(map[string][]map[string]interface{})
	order := make([]string, 0, len(items))
	for _, item := range items {
		guid, _ := item["guid"].(string)
		if _, ok := rowsByGUID[guid]; !ok {
			order = append(order, guid)
		}
		rowsByGUID[guid] = append(rowsByGUID[guid], item)
	}

	chunkIndex := 1
	for i := 0; i < len(order); i += chunkSize {
		end := i + chunkSize
		if end > len(order) {
			end = len(order)
		}
		chunkItems := make([]map[string]interface{}, 0)
		for _, guid := range order[i:end] {
			chunkItems = append(chunkItems, rowsByGUID[guid]...)
		}
		outputPath := filepath.Join(outputDir, fmt.Sprintf("part_%04d.json", chunkIndex))
		out, err := json.MarshalIndent(chunkItems, "", "  ")
		if err != nil {
			return err
		}
		if err := os.WriteFile(outputPath, out, 0644); err != nil {
			return err
		}
		chunkIndex++
	}

	return nil
}

func mergeJSONParts(inputDir, outputFile string) error {
	entries, err := os.ReadDir(inputDir)
	if err != nil {
		return err
	}

	sort.Slice(entries, func(i, j int) bool {
		return entries[i].Name() < entries[j].Name()
	})

	merged := make([]map[string]interface{}, 0)
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".json" {
			continue
		}
		path := filepath.Join(inputDir, entry.Name())
		data, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		var items []map[string]interface{}
		if err := json.Unmarshal(data, &items); err != nil {
			return err
		}
		merged = append(merged, items...)
	}

	out, err := json.MarshalIndent(merged, "", "  ")
	if err != nil {
		return err
	}

	return os.WriteFile(outputFile, out, 0644)
}

func splitCSVByGUID(inputFile string, chunkSize int, outputDir string) error {
	if chunkSize <= 0 {
		return fmt.Errorf("chunkSize must be > 0")
	}

	f, err := os.Open(inputFile)
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
		return fmt.Errorf("CSVファイルが空です: %s", inputFile)
	}

	guidIndex := -1
	textIndex := -1
	headers := records[0]
	for i, h := range headers {
		h = strings.TrimSpace(h)
		if h == "qa_id" {
			guidIndex = i
		}
		if h == "text" {
			textIndex = i
		}
	}
	if guidIndex == -1 {
		return fmt.Errorf("qa_id列が見つかりません: %s", inputFile)
	}

	if err := os.MkdirAll(outputDir, 0755); err != nil {
		return err
	}

	rowsByGUID := make(map[string][][]string)
	order := make([]string, 0, len(records))
	for _, rec := range records[1:] {
		guid := ""
		if guidIndex < len(rec) {
			guid = strings.TrimSpace(rec[guidIndex])
		}
		if _, ok := rowsByGUID[guid]; !ok {
			order = append(order, guid)
		}
		rowsByGUID[guid] = append(rowsByGUID[guid], rec)
	}

	chunkIndex := 1
	for i := 0; i < len(order); i += chunkSize {
		end := i + chunkSize
		if end > len(order) {
			end = len(order)
		}
		chunkRows := make([][]string, 0)
		for _, guid := range order[i:end] {
			chunkRows = append(chunkRows, rowsByGUID[guid]...)
		}
		outputPath := filepath.Join(outputDir, fmt.Sprintf("part_%04d.csv", chunkIndex))
		if err := writeCSVFile(outputPath, headers, chunkRows, textIndex); err != nil {
			return err
		}
		chunkIndex++
	}

	return nil
}

func mergeCSVParts(inputDir, outputFile string) error {
	entries, err := os.ReadDir(inputDir)
	if err != nil {
		return err
	}

	sort.Slice(entries, func(i, j int) bool {
		return entries[i].Name() < entries[j].Name()
	})

	var headers []string
	mergedRows := make([][]string, 0)
	textIndex := -1
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".csv" {
			continue
		}
		path := filepath.Join(inputDir, entry.Name())
		f, err := os.Open(path)
		if err != nil {
			return err
		}
		r := csv.NewReader(f)
		records, err := r.ReadAll()
		f.Close()
		if err != nil {
			return err
		}
		if len(records) == 0 {
			continue
		}
		if headers == nil {
			headers = records[0]
			for i, h := range headers {
				if strings.TrimSpace(h) == "text" {
					textIndex = i
					break
				}
			}
			if textIndex == -1 {
				return fmt.Errorf("text列が見つかりません: %s", path)
			}
		} else if len(records) > 0 {
			if !equalStringSlice(headers, records[0]) {
				return fmt.Errorf("CSVヘッダーが一致しません: %s", path)
			}
		}
		mergedRows = append(mergedRows, records[1:]...)
	}

	if headers == nil {
		return fmt.Errorf("CSVファイルが見つかりません: %s", inputDir)
	}

	return writeCSVFile(outputFile, headers, mergedRows, textIndex)
}

func writeCSVFile(outputFile string, headers []string, rows [][]string, textIndex int) error {
	outFile, err := os.Create(outputFile)
	if err != nil {
		return err
	}
	defer outFile.Close()

	if _, err := outFile.WriteString(strings.Join(headers, ",") + "\n"); err != nil {
		return err
	}

	headerLen := len(headers)
	for _, rec := range rows {
		row := make([]string, headerLen)
		for i := 0; i < headerLen; i++ {
			value := ""
			if i < len(rec) {
				value = rec[i]
			}
			if i == textIndex {
				row[i] = quoteCSVFieldAlways(value)
			} else {
				row[i] = quoteCSVField(value)
			}
		}
		if _, err := outFile.WriteString(strings.Join(row, ",") + "\n"); err != nil {
			return err
		}
	}

	return nil
}

func quoteCSVField(value string) string {
	if strings.ContainsAny(value, ",\n\r\"") {
		return "\"" + strings.ReplaceAll(value, "\"", "\"\"") + "\""
	}
	return value
}

func quoteCSVFieldAlways(value string) string {
	return "\"" + strings.ReplaceAll(value, "\"", "\"\"") + "\""
}

func equalStringSlice(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func mergeJSONAndCSVToCSV(jsonFile, csvFile, outputFile string) error {
	jsonData, err := os.ReadFile(jsonFile)
	if err != nil {
		return err
	}

	var items []map[string]interface{}
	if err := json.Unmarshal(jsonData, &items); err != nil {
		return err
	}

	jsonByGUID := make(map[string]map[string]string, len(items))
	for _, item := range items {
		guid, _ := item["guid"].(string)
		if guid == "" {
			continue
		}
		jsonByGUID[guid] = map[string]string{
			"category":   fmt.Sprintf("%v", item["category"]),
			"title":      fmt.Sprintf("%v", item["title"]),
			"original_q": fmt.Sprintf("%v", item["question"]),
			"original_a": fmt.Sprintf("%v", item["answer"]),
		}
	}

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
		h = strings.TrimSpace(h)
		if h == "qa_id" {
			guidIndex = i
		}
		if h == "text" {
			textIndex = i
		}
	}
	if guidIndex == -1 {
		return fmt.Errorf("qa_id列が見つかりません: %s", csvFile)
	}
	if textIndex == -1 {
		return fmt.Errorf("text列が見つかりません: %s", csvFile)
	}

	outFile, err := os.Create(outputFile)
	if err != nil {
		return err
	}
	defer outFile.Close()

	headers := []string{"guid", "category", "title", "original_q", "original_a", "altered_a"}
	if _, err := outFile.WriteString(strings.Join(headers, ",") + "\n"); err != nil {
		return err
	}

	for _, rec := range records[1:] {
		guid := ""
		if guidIndex < len(rec) {
			guid = strings.TrimSpace(rec[guidIndex])
		}
		if guid == "" {
			continue
		}
		text := ""
		if textIndex < len(rec) {
			text = rec[textIndex]
		}

		jsonRow, ok := jsonByGUID[guid]
		if !ok {
			continue
		}

		row := []string{
			guid,
			quoteCSVFieldAlways(jsonRow["category"]),
			quoteCSVFieldAlways(jsonRow["title"]),
			quoteCSVFieldAlways(jsonRow["original_q"]),
			quoteCSVFieldAlways(jsonRow["original_a"]),
			quoteCSVFieldAlways(text),
		}
		if _, err := outFile.WriteString(strings.Join(row, ",") + "\n"); err != nil {
			return err
		}
	}

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
